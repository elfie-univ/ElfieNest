import assert from 'node:assert/strict';
import {test} from 'node:test';
import {designMenu} from '../../../devtools/asset_design/web/design-state.mjs';
const index={groups:{layout:'家具布置',kit:'家具套装'},objects:[
 {id:'layout:central',collection:'layout:central',group:'layout',aggregate:true,versions:[{id:'composition',members:[]}]},
 ...[1,2,3].map(n=>({id:`layout:central:${n}`,collection:'layout:central',collectionLabel:'主楼布置',group:'layout',label:`主楼${n}楼`,versions:[{id:`floor${n}`}]})),
 {id:'layout:kit',collection:'layout:kit',group:'kit',label:'床桌椅套装',versions:[{id:'kit'}]},
 {id:'part:bed',collection:'layout:kit',group:'kit',label:'床体',versions:[{id:'bed'}]},
 {id:'layout:terraces',collection:'layout:terraces',group:'layout',aggregate:true,versions:[{id:'composition',members:[]}]},
 {id:'layout:terrace:M03',collection:'layout:terraces',group:'layout',module:'M03',versions:[{id:'m3'}]},
]};
test('content choices expose each central floor and furniture part, with one terrace choice',()=>{
 const menu=designMenu(index,'layout:central:2','floor2');
 assert.deepEqual(menu.groups.flatMap(g=>g.objects.map(o=>o.id)),['layout:central:1','layout:central:2','layout:central:3','layout:terraces','layout:kit','part:bed']);
 assert.equal(menu.object.id,'layout:central:2');
 assert.equal(menu.object.collection,'layout:central:2');
 assert.equal(menu.groups.find(g=>g.value==='kit').label,'家具');
 assert.equal(designMenu(index,'layout:terrace:M03','m3').object.id,'layout:terrace:M03');
});
test('object references survive revision changes and never borrow a different floor',async()=>{
 const {objectImages}=await import('../../../devtools/asset_design/web/content-images.mjs');
 const catalog={assets:[{files:['floor1.png','floor2.png','themes.png','pod.png','review.png'].map(path=>({path,kind:'image'}))}],imageReferences:[
  {path:'floor1.png',objects:['layout:central:1'],kind:'reference',title:'一层'},
  {path:'floor2.png',objects:['layout:central:2'],kind:'reference',title:'二层'},
  {path:'themes.png',objects:['layout:terraces'],kind:'reference',title:'共用八主题'},
  {path:'pod.png',objects:['layout:pod'],kind:'reference',title:'卧室'},
  {path:'review.png',objects:['layout:pod'],kind:'render',title:'检查',version:'v1'},
  {path:'unregistered.png',objects:['layout:pod'],kind:'reference',title:'未登记'},
 ]};
 assert.deepEqual(objectImages(catalog,'layout:central:1','v1').map(x=>x.path),['floor1.png']);
 assert.deepEqual(objectImages(catalog,'layout:central:1','v2').map(x=>x.path),['floor1.png']);
 assert.deepEqual(objectImages(catalog,'layout:terrace:M03','m3').map(x=>x.path),['themes.png']);
 assert.deepEqual(objectImages(catalog,'layout:pod','v2').map(x=>[x.path,x.kind]),[['pod.png','reference'],['review.png','history']]);
 assert.equal(objectImages(catalog,'layout:pod','v1')[1].kind,'render');
 assert.deepEqual(objectImages(catalog,'part:chair'),[]);
});
