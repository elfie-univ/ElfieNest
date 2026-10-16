// Selection and visibility never change adoption state.
export function adoptionLabel(object,version){return (object.current?.contentDigest&&version.contentDigest?object.current.contentDigest===version.contentDigest:object.current?.version===version.id)?'已确认':'未确认';}
export function versionRemovalScope(index,assetId){
 const objects=index.objects||[];
 const affected=objects.filter(o=>o.versions.some(v=>v.asset===assetId||v.sources?.some(s=>s.asset===assetId)));
 const usesSource=(object,version)=>objects.find(o=>o.id===object)?.versions.some(v=>(v.id===version||v.sources?.some(s=>s.asset===version))&&(v.asset===assetId||v.sources?.some(s=>s.asset===assetId)));
 return {labels:affected.filter(o=>!['overview','archive'].includes(o.group)&&!o.historical&&!o.aggregate).map(o=>o.label),
  protected:objects.some(o=>o.current&&(usesSource(o.id,o.current.version)||(o.current.refs||[]).some(r=>usesSource(r.object,r.version))))};
}
function collectionVersions(objects,base){
 const family=base?.collection||base?.id;
 const candidates=(base?.id==='overview'?[{id:'live',title:'当前确认组合'},...base.versions]:base?.versions||[]).map(v=>({...v,object:base.id,historical:!!base.historical}));
 for(const saved of objects.filter(o=>o.historical&&o.collection===family))for(const v of saved.versions){
  if(!candidates.some(candidate=>candidate.id===v.id))candidates.push({...v,object:saved.id,historical:true});
 }
 const versions=[],contents=new Map();
 for(const candidate of candidates){
  const same=candidate.contentDigest&&!candidate.sourceOnly?contents.get(candidate.contentDigest):null;
  if(same){same.aliases.push(candidate.id,...(candidate.sources||[]).map(s=>s.asset));continue;}
  const version={...candidate,aliases:[candidate.id,...(candidate.sources||[]).map(s=>s.asset)]};
  versions.push(version);
  if(candidate.contentDigest&&!candidate.sourceOnly)contents.set(candidate.contentDigest,version);
 }
 return versions;
}
export function designMenu(index,objectId='overview',versionId=''){
 const hasFloors=index.objects?.some(o=>/^layout:central:[123]$/.test(o.id));
 const names={'layout:central:1':'主楼一层布置','layout:central:2':'主楼二层布置','layout:central:3':'主楼三层布置','layout:pod':'小屋一层卧室','layout:terraces':'小屋二层露台'};
 const objects=(index.objects||[]).filter(o=>!hasFloors||o.collection!=='layout:central'||/^layout:central:[123]$/.test(o.id)).map(o=>{
  const individual=/^layout:central:[123]$/.test(o.id)||o.id.startsWith('part:');
  const label=names[o.id]||(o.collection==='layout:terraces'?'小屋二层露台':o.label);
  return {...o,label,collection:individual?o.id:o.collection,collectionLabel:individual?label:names[o.collection]||o.collectionLabel};
 });
 const requested=objects.find(o=>o.id===objectId)||objects.find(o=>o.collection===objectId)||objects.find(o=>o.id==='overview')||objects[0];
 const family=requested?.collection||requested?.id;
 const base=requested?.historical?(objects.find(o=>o.id===family)||requested):requested;
 const versions=collectionVersions(objects,base);
 const selected=versions.find(v=>v.aliases.includes(versionId))||versions[0];
 const object=objects.find(o=>o.id===selected?.object)||base;
 const seen=new Set(),collections=[];
 for(const candidate of objects){const id=candidate.collection||candidate.id;if(seen.has(id))continue;seen.add(id);
  const choices=id===family?versions:collectionVersions(objects,objects.find(o=>o.id===id)||candidate);
  collections.push({...candidate,id,label:candidate.collectionLabel||candidate.label,
   compositionOnly:choices.length>0&&choices.every(v=>v.id==='live'||v.members),
   versionCount:choices.filter(v=>v.id!=='live'&&!v.members&&!v.sourceOnly).length,sourceCount:choices.filter(v=>v.sourceOnly).length});
 }
 return {object,versions,selected,groups:Object.entries(index.groups).map(([value,label])=>({value,label:value==='kit'?'家具':label,objects:collections.filter(o=>o.group===value)})).filter(g=>g.objects.length)};
}
export function sceneVisibility(properties,view,object){
 if(properties.designReference&&!view.context)return false;
 if(object==='overview'&&properties.furniture&&!view.furniture)return false;
 return true;
}
export function sceneMeshSelection(mesh,associations,selected){
 for(let node=mesh;node;node=node.parent){
  const index=associations.get(node)?.nodes;
  if(index!==undefined)return selected.has(index);
 }
 return false;
}

// Rewrite only the in-memory scene graph; original geometry and saved files stay intact.
export function subsetGLB(buffer,selected){
 const header=new DataView(buffer),oldLength=header.getUint32(12,true);
 const doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,oldLength)));
 const retained=new Set(),visiting=new Set();
 function keep(index){
  if(visiting.has(index))throw new Error('模型节点循环引用');
  visiting.add(index);
  const node=doc.nodes[index],children=(node.children||[]).filter(keep);
  if(node.children)node.children=children;
  if(!selected.has(index))delete node.mesh;
  const used=selected.has(index)||children.length>0;
  if(used)retained.add(index);
  visiting.delete(index);return used;
 }
 const scene=doc.scenes[doc.scene||0];scene.nodes=scene.nodes.filter(keep);
 for(let i=0;i<doc.nodes.length;i++)if(!selected.has(i))delete doc.nodes[i].mesh;
 if(doc.animations)doc.animations=doc.animations.map(a=>({...a,channels:a.channels.filter(c=>retained.has(c.target.node))})).filter(a=>a.channels.length);
 const json=new TextEncoder().encode(JSON.stringify(doc)),length=Math.ceil(json.length/4)*4;
 const tail=new Uint8Array(buffer,20+oldLength),result=new ArrayBuffer(20+length+tail.length),output=new DataView(result);
 new Uint8Array(result,0,20).set(new Uint8Array(buffer,0,20));
 output.setUint32(8,result.byteLength,true);output.setUint32(12,length,true);
 new Uint8Array(result,20,length).fill(32);new Uint8Array(result,20,json.length).set(json);
 new Uint8Array(result,20+length).set(tail);return result;
}

// Reuse instance transforms from the source GLB, including reflection and parent transforms.
export function placementTransforms(doc,anchors,THREE){
 const world=new Map();
 function visit(index,parent){
  const node=doc.nodes[index],local=node.matrix?new THREE.Matrix4().fromArray(node.matrix):new THREE.Matrix4().compose(
   new THREE.Vector3(...(node.translation||[0,0,0])),new THREE.Quaternion(...(node.rotation||[0,0,0,1])),new THREE.Vector3(...(node.scale||[1,1,1])));
  const matrix=parent.clone().multiply(local);world.set(index,matrix);
  for(const child of node.children||[])visit(child,matrix);
 }
 for(const node of doc.scenes[doc.scene||0].nodes)visit(node,new THREE.Matrix4());
 const entries=Object.entries(anchors),source=world.get(entries[0]?.[1]);
 if(!source)throw new Error('小屋定位缺失');
 const inverse=source.clone().invert();
 return entries.map(([module,node])=>{
  if(!world.has(node))throw new Error('小屋定位缺失');
  return {module,matrix:world.get(node).clone().multiply(inverse)};
 });
}

export function filePreviewSelection(index,asset,file,currentObject){
 if(!asset?.files?.some(f=>f.path===file&&f.kind==='model'&&/\.(glb|gltf)$/i.test(file)))return null;
 const owners=index.objects.filter(o=>o.versions.some(v=>v.asset===asset.id));
 const object=owners.find(o=>o.id===currentObject)||owners.find(o=>o.historical)||owners[0];
 const version=object?.versions.find(v=>v.asset===asset.id);
 return version?{object:object.id,version:version.id,file}:null;
}

// People are saved scene geometry, independent of editable objects and reference buildings.
// Keep their original world placements, once per module/floor, instead of cloning M01 people.
export function sceneReferenceLayer(doc,layers,claimed){
 const records=[];
 function visit(index,inherited){
  const node=doc.nodes[index],properties={...inherited,...node.extras};
  if(node.mesh!==undefined&&properties.reference===true)records.push({index,...properties});
  for(const child of node.children||[])visit(child,properties);
 }
 for(const index of doc.scenes[doc.scene||0].nodes)visit(index,{});
 const eligible=records.filter(record=>layers.some(layer=>
  (!layer.module||layer.module===record.module||Object.hasOwn(layer.placements||{},record.module))
  &&(!layer.floor||String(layer.floor)===String(record.floor||1))));
 const originals=eligible.filter(r=>r.reference_id===`${r.module}-${r.floor||1}`);
 const canonical=new Set(originals.map(r=>`${r.module}:${r.floor||1}`));
 const people=eligible.filter(r=>!canonical.has(`${r.module}:${r.floor||1}`)||r.reference_id===`${r.module}-${r.floor||1}`);
 const fresh=new Set(people.map(r=>`${r.module}:${r.floor||1}`).filter(key=>!claimed.has(key)));
 for(const key of fresh)claimed.add(key);
 return {nodes:people.filter(r=>fresh.has(`${r.module}:${r.floor||1}`)).map(r=>r.index),
  object:'helpers',group:'helper',reference:false};
}
