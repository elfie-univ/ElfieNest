import assert from 'node:assert/strict';
import {test} from 'node:test';
import {designMenu,adoptionLabel,sceneVisibility,sceneMeshSelection,versionRemovalScope} from '../../../devtools/asset_design/web/design-state.mjs';

test('source deletion identifies every affected object and protects confirmed dependencies',()=>{
 const index={objects:[
  {id:'overview',group:'overview',label:'园区总览',versions:[{id:'v1',asset:'source'}]},
  {id:'shell',group:'building',label:'小屋',versions:[{id:'v1',asset:'source'}]},
  {id:'layout',group:'layout',label:'小屋家具布置',versions:[{id:'v1',asset:'source'},{id:'v2',asset:'other'}],
   current:{version:'v2',refs:[{object:'shell',version:'v1'}]}},
  {id:'archive',group:'archive',label:'原始资产',versions:[{id:'v1',asset:'source'}]},
 ]};
 assert.deepEqual(versionRemovalScope(index,'source'),{labels:['小屋','小屋家具布置'],protected:true});
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
  {id:'layout:kit',collection:'layout:kit',collectionLabel:'床桌椅套装',label:'床桌椅套装',group:'kit',versions:[{id:'kit'}]},
  {id:'part:bed',collection:'layout:kit',collectionLabel:'床桌椅套装',label:'床体',group:'kit',versions:[{id:'kit'}]},
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
