import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {confirmedReferenceSignature,designMenu,adoptionLabel,sceneVisibility,sceneMeshSelection,versionRemovalScope} from '../../../devtools/asset_design/web/design-state.mjs';

test('furniture menu lists only opted-in reusable masters without removing scene objects',()=>{
 const part=(id,extra={})=>({id,group:'kit',label:id,versions:[{id:id+'-v1'}],...extra});
 const index={groups:{overview:'园区总览',layout:'家具布置',kit:'家具套装'},objects:[
  {id:'overview',group:'overview',label:'完整园区',versions:[]},
  {id:'layout:pod',group:'layout',label:'卧室组装',versions:[{id:'room'}]},
  part('part:single'),part('part:drawer',{menuVisible:false}),
  part('part:chair',{menuVisible:true,menuLabel:'共用椅子',menuOrder:2}),
  part('part:bed',{menuVisible:true,menuLabel:'共用床体',menuOrder:1}),
 ]};
 const frozen=JSON.stringify(index),menu=designMenu(index);
 assert.deepEqual(menu.groups.find(g=>g.value==='kit').objects.map(o=>[o.id,o.label]),[
  ['part:bed','共用床体'],['part:chair','共用椅子'],
 ]);
 assert(menu.groups.find(g=>g.value==='layout').objects.some(o=>o.id==='layout:pod'));
 assert.equal(designMenu(index,'part:drawer').selected.id,'part:drawer-v1','hidden exports remain addressable');
 assert.equal(JSON.stringify(index),frozen,'visibility does not delete objects, versions or scene data');
});

test('publishing a floor layout opens it from its building without adopting either object',async()=>{
 const {publishedPreview}=await import('../../../devtools/asset_design/web/design-state.mjs');
 const building={id:'building:central',module:'central',group:'building',versions:[{id:'b21'}],current:{version:'b19'}};
 const layout={id:'layout:central:1',module:'central',floor:'1',group:'layout',versions:[{id:'l33',asset:'l33'}],current:{version:'l32'}};
 const index={objects:[building,layout]},before={assets:[{id:'b21'}]},after={assets:[...before.assets,{id:'l33',designObject:{id:layout.id},designVersion:{id:'l33'}}]};
 const frozen=JSON.stringify(index);
 assert.deepEqual(publishedPreview(before,after,index,building.id,{module:'central',floor:'1'}),{object:layout.id,version:'l33'});
 assert.equal(publishedPreview(after,after,index,building.id,{module:'central',floor:'1'}),null);
 assert.equal(publishedPreview(before,after,index,building.id,{module:'central',floor:'2'}),null);
 assert.equal(JSON.stringify(index),frozen);
});

test('publication follows current content, refreshes overview and ignores unrelated modules',async()=>{
 const {publishedPreview}=await import('../../../devtools/asset_design/web/design-state.mjs');
 const item=(id,module,group='building')=>({id,module,group,versions:[{id:id+'2',asset:id+'2'},{id:id+'1'}]});
 const central=item('building:central','central'),pod=item('building:pod','M01'),plant=item('part:plant','','kit');
 const index={objects:[{id:'overview',group:'overview'},central,pod,plant]};
 const before={assets:[]};
 const after={assets:[central,pod,plant].map(o=>({id:o.id+'2',designObject:{id:o.id},designVersion:{id:o.id+'2'}}))};
 assert.deepEqual(publishedPreview(before,after,index,central.id,{module:'central',floor:'1'}),{object:central.id,version:central.id+'2'});
 assert.deepEqual(publishedPreview(before,after,index,plant.id,{}),{object:plant.id,version:plant.id+'2'});
 assert.deepEqual(publishedPreview(before,after,index,'overview',{module:'central',floor:'1'}),{object:central.id,version:central.id+'2'});
 assert.equal(publishedPreview(before,{assets:[after.assets[1]]},index,central.id,{module:'central'}),null);
 assert.equal(publishedPreview(before,{assets:[{...after.assets[0],designVersion:{id:'not-indexed-yet'}}]},index,central.id,{module:'central'}),null);
});

test('open workbench polls publications, retries incomplete reads and preserves view and orbit',async()=>{
 const web=new URL('../../../devtools/asset_design/web/',import.meta.url);
 const dependencies=Object.assign({},...await Promise.all(['content-images.mjs','design-state.mjs','view-state.mjs','asset-media.mjs'].map(name=>import(new URL(name,web)))));
 const building={id:'building:central',group:'building',module:'central',label:'主楼',versions:[{id:'b21',asset:'b21',file:'b21.glb'},{id:'b19',asset:'b19',file:'b19.glb'}]};
 const layout={id:'layout:central:1',group:'layout',module:'central',floor:'1',label:'一楼',versions:[{id:'l33',asset:'l33',file:'l33.glb'}]};
 const asset=(id,object)=>({id,title:id,category:'other',primaryModel:id+'.glb',models:[id+'.glb'],images:[],files:[{path:id+'.glb',name:id+'.glb',kind:'model',bytes:100}],designObject:{id:object.id},designVersion:{id}});
 let catalog={assets:[asset('b19',building),asset('b21',building)],stats:{}},index={groups:{building:'建筑',layout:'布置'},objects:[building]};
 const nodes=new Map(),events=new Map(),timers=[],requests=[],messages=[],warnings=[];
 const element=()=>({dataset:{},style:{},children:[],value:'',hidden:false,classList:{toggle(){},remove(){}},append(...children){this.children.push(...children);},replaceChildren(){this.children=[];},get options(){return this.children;},setAttribute(){},removeAttribute(){}});
 const document={hidden:false,getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},createElement:element,addEventListener(name,fn){events.set(name,fn);}};
 const location={hash:'#view=model&designObject=building%3Acentral&revision=b21&asset=b21&object=central&floor=1&light=dusk&glass=0&dimensions=1',origin:'http://127.0.0.1'};
 const orbit={position:[4,3,8],target:[1,2,3]};
 document.getElementById('viewer').contentWindow={elfiePreview:{orbit:()=>orbit},postMessage(message){messages.push(message);}};
 let fail=false;
 const context={...dependencies,document,location,URLSearchParams,console:{warn(...args){warnings.push(args);}},setTimeout(fn){timers.push(fn);return timers.length;},clearTimeout(){},history:{replaceState(_,__,hash){location.hash=hash;}},fetch:async (path,options={})=>{
  requests.push(path);if(fail)throw new Error('service restarting');
  const etag=JSON.stringify(catalog);
  if(path.endsWith('catalog.json')&&options.headers?.['If-None-Match']===etag)return {status:304};
  return {ok:true,status:200,headers:{get:()=>etag},json:async()=>structuredClone(path.endsWith('catalog.json')?catalog:index)};
 }};
 context.window={addEventListener(name,fn){events.set(name,fn);}};
 const source=(await readFile(new URL('catalog-request.mjs',web),'utf8')).replace(/^export /gm,'')+'\n'+(await readFile(new URL('library.js',web),'utf8')).replace(/^import .*;\n/gm,'');
 const page=await vm.runInNewContext('(async()=>{'+source+'\nreturn {refreshCatalog};})()',context);
 assert.equal(timers.length,1);
 assert.equal(nodes.get('assetSelect').value,'b21');
 await timers[0]();
 assert.equal(requests.filter(p=>p.endsWith('/index')).length,1,'unchanged catalogue does not rebuild the index');
 catalog.assets.push(asset('l33',layout));
 await page.refreshCatalog();
 assert.equal(nodes.get('assetSelect').value,'b21','incomplete index retains the pending publication');
 index.objects.push(layout);fail=true;
 await page.refreshCatalog();assert.equal(warnings.length,1);
 fail=false;nodes.get('viewer').dataset.ready='yes';
 await page.refreshCatalog();
 assert.equal(nodes.get('assetSelect').value,'l33');
 assert.equal(nodes.get('categorySelect').value,layout.id);
 assert.match(nodes.get('viewer').src,/revision=l33/);
 const params=new URLSearchParams(location.hash.slice(1));
 assert.equal(params.get('floor'),'1');assert.equal(params.get('light'),'dusk');assert.equal(params.get('glass'),'0');assert.equal(params.get('dimensions'),'1');
 events.get('message')({origin:location.origin,source:nodes.get('viewer').contentWindow,data:{type:'asset-ready',asset:'l33',file:'l33.glb',designObject:layout.id,revision:'l33',capabilities:{central:['1','2']}}});
 assert.deepEqual(messages.at(-1).orbit,orbit);
 // A reader can still inspect history; the next poll must not force them back.
 nodes.get('categorySelect').value=building.id;nodes.get('categorySelect').onchange();
 nodes.get('assetSelect').value='b19';nodes.get('assetSelect').onchange();
 await page.refreshCatalog();assert.equal(nodes.get('assetSelect').value,'b19');
 // An unnumbered draft refreshes even when the published catalogue is unchanged.
 building.versions.unshift({id:'draft',title:'主楼 · 工作稿（未编号）',draft:true,asset:'b21',file:'source.glb',digest:'first'});
 catalog.assets[0].description='draft preview enabled';await page.refreshCatalog();
 nodes.get('assetSelect').value='draft';nodes.get('assetSelect').onchange();
 assert.equal(nodes.get('deleteAsset').hidden,true);
 nodes.get('viewer').dataset.ready='yes';
 building.versions[0].digest='second';const oldIndexReads=requests.filter(p=>p.endsWith('/index')).length;
 await page.refreshCatalog();assert.equal(nodes.get('assetSelect').value,'draft');
 assert.equal(requests.filter(p=>p.endsWith('/index')).length,oldIndexReads+1);
 const frame=nodes.get('viewer'),reloads=[];let frameSource=frame.src;
 Object.defineProperty(frame,'src',{get:()=>frameSource,set(value){frameSource=value;reloads.push(value);},configurable:true});
 frame.dataset.ready='yes';
 index.objects.push({id:'building:pod',group:'building',module:'M01',label:'小屋',versions:[{id:'draft',draft:true,asset:'b21',file:'pod.glb',digest:'unrelated'}]});
 await page.refreshCatalog();assert.equal(reloads.length,0,'an unrelated draft edit does not reload the open model');
 building.versions[0].digest='third';frame.dataset.ready='no';
 await page.refreshCatalog();assert.equal(reloads.length,0,'a draft update does not interrupt a preview still loading');
 frame.dataset.ready='yes';await page.refreshCatalog();assert.equal(reloads.length,1,'the latest draft is applied after loading completes');
 events.get('message')({origin:location.origin,source:frame.contentWindow,data:{type:'asset-ready',asset:'b21',file:'source.glb',designObject:building.id,revision:'draft',capabilities:{central:['1','2']},designPlan:{layers:[{object:layout.id,reference:true}]}}});
 layout.versions.unshift({id:'draft',draft:true,asset:'l33',file:'floor.glb',digest:'floor-draft'});
 await page.refreshCatalog();assert.equal(reloads.length,1,'unconfirmed reference drafts do not change the preview');
 layout.current={id:'confirmed-layout',version:'l33'};
 await page.refreshCatalog();assert.equal(reloads.length,2,'a newly confirmed reference updates the preview');
 document.hidden=true;const count=requests.length;await page.refreshCatalog();assert.equal(requests.length,count);
 assert(requests.every(path=>!path.includes('/confirm')));
});

test('source deletion protects only the objects current version',()=>{
 const index={objects:[
  {id:'overview',group:'overview',label:'园区总览',versions:[{id:'v1',asset:'source'}]},
  {id:'shell',group:'building',label:'小屋',versions:[{id:'v1',asset:'source'}]},
  {id:'layout',group:'layout',label:'小屋家具布置',versions:[{id:'v1',asset:'source'},{id:'v2',asset:'other'}],
   current:{version:'v2',refs:[{object:'shell',version:'v1'}]}},
  {id:'archive',group:'archive',label:'原始资产',versions:[{id:'v1',asset:'source'}]},
 ]};
 assert.deepEqual(versionRemovalScope(index,'source'),{labels:['小屋','小屋家具布置'],protected:false});
 delete index.objects[2].current;
 assert.deepEqual(versionRemovalScope(index,'source'),{labels:['小屋','小屋家具布置'],protected:false});
 assert.deepEqual(versionRemovalScope(index,'missing'),{labels:[],protected:false});
});

test('grouped objects use newest draft, while total has a distinct live choice',()=>{
 const state={groups:{overview:'园区总览',building:'建筑本体',landscape:'室外环境'},objects:[
  {id:'overview',group:'overview',label:'完整园区',versions:[{id:'old'}]},
  {id:'building:M01',group:'building',label:'小屋 M01',current:{version:'v9'},versions:[{id:'v10',title:'draft'},{id:'v9',title:'old'}]},
 ]};
 assert.equal(designMenu(state,'building:M01').selected.id,'v10');
 assert.equal(designMenu(state,'building:M01','v9').selected.id,'v9');
 assert.equal(designMenu(state,'overview').selected.id,'live');
 assert(!designMenu(state,'overview').groups.some(g=>g.value==='landscape'));
 assert.equal(adoptionLabel(state.objects[1],{id:'v9'}),'已确认');
});
test('reference visibility never hides editable furniture and toggles no versions',()=>{
 const main={designLayer:true,designEditable:true,furniture:true};
 const ref={designLayer:true,designReference:true,furniture:true};
 assert(sceneVisibility(main,{context:false,furniture:false},'layout:M01:1'));
 assert(!sceneVisibility(ref,{context:false},'layout:M01:1'));
 assert(sceneVisibility(ref,{context:true,furniture:false},'building:M01'));
 assert(!sceneVisibility(main,{furniture:false},'overview'));
});
test('subset selection resolves primitive node ancestry and retains only selected nodes',()=>{
 const parent={parent:null},child={parent};
 const associations=new Map([[parent,{nodes:7}],[child,{meshes:0,primitives:0}]]);
 assert(sceneMeshSelection(child,associations,new Set([7])));
 assert(!sceneMeshSelection(child,associations,new Set([3])));
});

test('GLB subset preserves node identities and transforms without parsing unrelated geometry',async()=>{
 const {subsetGLB}=await import('../../../devtools/asset_design/web/design-state.mjs');
 const doc={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0,3]}],nodes:[
  {translation:[10,0,0],children:[1,2]}, {mesh:0}, {mesh:1}, {mesh:2},
 ]};
 const json=new TextEncoder().encode(JSON.stringify(doc));
 const length=Math.ceil(json.length/4)*4,buffer=new ArrayBuffer(20+length+12),view=new DataView(buffer);
 view.setUint32(0,0x46546c67,true);view.setUint32(4,2,true);view.setUint32(8,buffer.byteLength,true);
 view.setUint32(12,length,true);view.setUint32(16,0x4e4f534a,true);
 new Uint8Array(buffer,20,length).fill(32);new Uint8Array(buffer,20,json.length).set(json);
 new Uint8Array(buffer,20+length).set([4,0,0,0,66,73,78,0,1,2,3,4]);
 const sliced=subsetGLB(buffer,new Set([1])),output=new DataView(sliced);
 const result=JSON.parse(new TextDecoder().decode(new Uint8Array(sliced,20,output.getUint32(12,true))));
 assert.deepEqual(result.scenes[0].nodes,[0]);assert.deepEqual(result.nodes[0].children,[1]);
 assert.deepEqual(result.nodes[0].translation,[10,0,0]);assert.equal(result.nodes[1].mesh,0);
 assert.equal(result.nodes[2].mesh,undefined);assert.equal(result.nodes.length,4);
 assert.deepEqual([...new Uint8Array(sliced).slice(-4)],[1,2,3,4]);
 assert.equal(JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,length))).nodes[2].mesh,1);
});

test('one house template reuses source instance placement including mirrors',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {placementTransforms}=await import('../../../devtools/asset_design/web/design-state.mjs');
 const doc={scene:0,scenes:[{nodes:[0]}],nodes:[{translation:[5,0,0],children:[1,2]},
  {translation:[10,0,0]}, {translation:[0,0,12],scale:[-1,1,1]},
 ]};
 const poses=placementTransforms(doc,{M01:1,M02:2},THREE);
 const sourcePoint=new THREE.Vector3(16,0,0);
 assert.deepEqual(sourcePoint.clone().applyMatrix4(poses[0].matrix).toArray(),[16,0,0]);
 assert.deepEqual(sourcePoint.clone().applyMatrix4(poses[1].matrix).toArray(),[4,0,12]);
 assert.deepEqual(poses.map(p=>p.module),['M01','M02']);
});

test('content menu keeps floor and part versions independent from old combined exports',()=>{
 const index={groups:{layout:'家具布置',kit:'家具套装'},objects:[
  {id:'layout:central',collection:'layout:central',collectionLabel:'主楼布置',label:'主楼布置',group:'layout',aggregate:true,versions:[{id:'v2'}]},
  {id:'layout:central:2',collection:'layout:central',collectionLabel:'主楼布置',label:'主楼二楼布置',group:'layout',versions:[{id:'v2'}]},
  {id:'saved:old',collection:'layout:central',collectionLabel:'主楼布置',label:'历史整套',group:'layout',historical:true,versions:[{id:'v1',asset:'old'}]},
  {id:'layout:kit',collection:'layout:kit',collectionLabel:'床桌椅套装',label:'床桌椅套装',group:'kit',menuVisible:true,versions:[{id:'kit'}]},
  {id:'part:bed',collection:'layout:kit',collectionLabel:'床桌椅套装',label:'床体',group:'kit',menuVisible:true,versions:[{id:'kit'}]},
 ]};
 const menu=designMenu(index,'layout:central:2','v1');
 assert.deepEqual(menu.groups.flatMap(g=>g.objects.map(o=>o.id)),['layout:central:2','layout:kit','part:bed']);
 assert.equal(menu.object.id,'layout:central:2');
 assert.equal(menu.selected.id,'v2');
 assert.equal(designMenu(index,'part:bed','kit').object.id,'part:bed');
});

test('registered supplementary files preview in their own scope without falling back to overview',async()=>{
 const {filePreviewSelection}=await import('../../../devtools/asset_design/web/design-state.mjs');
 const asset={id:'kit',files:[{path:'kit/whole.glb',kind:'model'},{path:'kit/throw.glb',kind:'model'},{path:'kit/source.blend',kind:'source'}]};
 const index={objects:[{id:'overview',versions:[]},{id:'part:bedding',versions:[{id:'v1',asset:'kit',file:'kit/whole.glb'}]}]};
 assert.deepEqual(filePreviewSelection(index,asset,'kit/throw.glb','part:bedding'),{object:'part:bedding',version:'v1',file:'kit/throw.glb'});
 assert.equal(filePreviewSelection(index,asset,'secret.glb','part:bedding'),null);
 assert.equal(filePreviewSelection(index,asset,'kit/source.blend','part:bedding'),null);
});

test('historical reference descriptions are not treated as measurement-marker flags',async()=>{
 const {frameable,meshVisible,deriveCapabilities}=await import('../../../devtools/asset_design/web/view-state.mjs');
 const record={module:'M01',floor:1,reference:'Approved isolated bed/desk image'};
 const view={module:'all',floor:'all',scale:false,glass:true,furniture:true};
 assert(frameable(record,'Bed shell',{}));
 assert(meshVisible(record,view));
 assert.deepEqual(deriveCapabilities([record]),{M01:['1']});
 assert(!frameable({...record,reference:true},'Height marker',{}));
 assert(!meshVisible({...record,reference:true},view));
});

test('composition retains original people per module and floor without duplicating references',async()=>{
 const {sceneReferenceLayer}=await import('../../../devtools/asset_design/web/design-state.mjs');
 const doc={scene:0,scenes:[{nodes:[0,4,5,6]}],nodes:[
  {extras:{module:'M01'},children:[1,2,3]},
  {mesh:0,extras:{reference:true,floor:1,reference_id:'M01-1'}},
  {mesh:0,extras:{reference:true,floor:2,reference_id:'M01-2'}},
  {mesh:1,extras:{furniture:true}},
  {mesh:0,extras:{reference:true,module:'M02',floor:1,reference_id:'M02-1'}},
  {mesh:0,extras:{reference:true,module:'central',floor:1}},
  {mesh:0,extras:{reference:true,module:'M02',floor:1,reference_id:'M01-1'}},
 ]};
 const claimed=new Set();
 const layers=[{module:'M01',nodes:[3],placements:{M01:0,M02:4}}];
 const refs=sceneReferenceLayer(doc,layers,claimed);
 assert.deepEqual(refs.nodes,[1,2,4]);
 assert.equal(refs.reference,false);
 assert.equal(refs.group,'helper');
 assert.equal(refs.placements,undefined);
 assert.deepEqual(sceneReferenceLayer(doc,layers,claimed).nodes,[]);
 assert.deepEqual(sceneReferenceLayer(doc,[{module:'M01',floor:'2',nodes:[3]}],new Set()).nodes,[2]);
 assert(sceneVisibility({reference:true,designReference:false},{context:false},'layout:pod'));
});

test('carried export bookmarks resolve within their object and adoption follows content',()=>{
 const state={groups:{building:'建筑本体'},objects:[{id:'building:central',label:'主楼',group:'building',
  current:{version:'original',contentDigest:'same'},versions:[{id:'original',asset:'original',title:'主楼 · V001',contentDigest:'same',sources:[{asset:'original'},{asset:'pod_edit'}]}]}]};
 assert.equal(designMenu(state,'building:central','pod_edit').selected.id,'original');
 assert.equal(adoptionLabel(state.objects[0],{id:'copy',contentDigest:'same'}),'已确认');
 assert.equal(adoptionLabel(state.objects[0],{id:'original',contentDigest:'changed'}),'未确认');
 assert.equal(versionRemovalScope(state,'pod_edit').protected,true);
});

test('collection counts use distinct contents, retain unknown sources and resolve hidden copies',()=>{
 const index={groups:{overview:'总览',building:'建筑'},objects:[
  {id:'overview',group:'overview',label:'完整园区',versions:[{id:'a',contentDigest:'whole'},{id:'b',contentDigest:'whole'}]},
  {id:'house',group:'building',label:'小屋',versions:[{id:'confirmed',contentDigest:'same',sources:[{asset:'confirmed'}]}]},
  {id:'saved:copy',collection:'house',group:'building',historical:true,versions:[{id:'copy',asset:'copy',contentDigest:'same'}]},
  {id:'saved:other',collection:'house',group:'building',historical:true,versions:[{id:'other',contentDigest:'different'}]},
  {id:'saved:source',collection:'house',group:'building',historical:true,versions:[{id:'source',sourceOnly:true}]},
 ]};
 const menu=designMenu(index,'house','copy');
 assert.deepEqual(menu.versions.map(v=>v.id),['confirmed','other','source']);
 assert.equal(menu.selected.id,'confirmed');
 assert.equal(menu.groups[1].objects[0].versionCount,2);
 assert.equal(menu.groups[1].objects[0].sourceCount,1);
 assert.equal(menu.groups[0].objects[0].versionCount,1);
 assert.equal(designMenu(index,'overview','b').selected.id,'a');
 assert.equal(index.objects[1].versions[0].sources.length,1);
});

test('object-reference compositions are views rather than saved revisions',()=>{
 const index={groups:{layout:'家具布置'},objects:[{id:'layout:central',collection:'layout:central',label:'主楼布置',group:'layout',aggregate:true,
  versions:[{id:'composition',members:[{object:'layout:central:1',version:'v1'}]}]}]};
 const object=designMenu(index,'layout:central').groups[0].objects[0];
 assert.equal(object.compositionOnly,true);
 assert.equal(object.versionCount,0);
});

test('reference refresh watches confirmed versions, not unconfirmed publications',()=>{
 const index={objects:[{id:'host',current:{id:'h',version:'h1'}},{id:'ref',current:{id:'r',version:'r1'},versions:[{id:'r2'}]}]};
 const plan={layers:[{object:'ref',reference:true}],templates:[]};
 const first=confirmedReferenceSignature(index,'host',plan);
 index.objects[1].versions.unshift({id:'r3'});
 assert.equal(confirmedReferenceSignature(index,'host',plan),first);
 index.objects[1].current={id:'new',version:'r3'};
 assert.notEqual(confirmedReferenceSignature(index,'host',plan),first);
});

 test('reference refresh observes newly confirmed missing references and overview members',()=>{
 const index={objects:[{id:'building'},{id:'layout',current:{id:'first',version:'v1'}}]};
 const plan={layers:[{object:'layout',reference:false}],issues:[{object:'building',reason:'待确认'}]};
 const first=confirmedReferenceSignature(index,'overview',plan);
 index.objects[0].current={id:'confirmed',version:'b1'};
 assert.notEqual(confirmedReferenceSignature(index,'overview',plan),first);
 const second=confirmedReferenceSignature(index,'overview',plan);
 index.objects[1].current={id:'second',version:'v2'};
 assert.notEqual(confirmedReferenceSignature(index,'overview',plan),second);
 });
