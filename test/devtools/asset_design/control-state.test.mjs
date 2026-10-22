import assert from 'node:assert/strict';
import {test} from 'node:test';
import {
  deriveCapabilities, floorChoices, objectChoices, normalizeView,
  readView, writeView, meshVisible, frameable, measurementVisible,
  spansFloors, floorControlVisible,
} from '../../../devtools/asset_design/web/view-state.mjs';
import {assetModes} from '../../../devtools/asset_design/web/asset-media.mjs';

const records = [1,2,3,4].map(floor=>({module:'central',floor}));
for(let i=1;i<=8;i++) for(const floor of [1,2]) records.push({module:`M${String(i).padStart(2,'0')}`,floor});
const capabilities=deriveCapabilities(records);

test('the actual upper slab supplies the selected room ceiling only in whole view',()=>{
 const slab={module:'central',floor:2,ceiling_for_floor:1};
 const view={module:'central',floor:'1',section:false,glass:true,furniture:true,scale:true};
 assert.equal(meshVisible(slab,view),true);
 assert.equal(meshVisible(slab,{...view,section:true}),false);
 assert.equal(meshVisible(slab,{...view,floor:'2',section:true}),true);
 assert.equal(meshVisible(slab,{...view,floor:'all',section:true}),true);
 assert.equal(meshVisible(slab,{...view,module:'M01'}),false);
});

test('top navigation contains model, images and comparison only',()=>{
  const asset={primaryModel:'estate.glb',models:['estate.glb','chair.glb'],images:['reference.png'],files:[{path:'estate.glb',kind:'model'},{path:'reference.png',kind:'image'}]};
  const choices=assetModes(asset,{assets:[asset]});
  assert.deepEqual(choices.map(c=>c.value),['model','images','compare']);
});
test('object selection supports the eight houses together',()=>{
  assert(objectChoices(capabilities).some(c=>c.value==='pods'));
  assert.equal(objectChoices(capabilities).filter(c=>/^M\d+$/.test(c.value)).length,8);
});
test('floors belong to the selected object',()=>{
  assert.deepEqual(floorChoices(capabilities,'all').map(c=>c.value),['all','1','2','3','4']);
  assert.deepEqual(floorChoices(capabilities,'central').map(c=>c.label),['全部楼层','一楼','二楼','三楼','屋顶']);
  assert.deepEqual(floorChoices(capabilities,'M01').map(c=>c.label),['全部楼层','一楼','二楼露台']);
  assert.deepEqual(floorChoices(capabilities,'pods').map(c=>c.value),['all','1','2']);
  assert.deepEqual(objectChoices(deriveCapabilities([])),[{value:'all',label:'完整模型'}]);
});
test('a floor layout keeps the reference-building floor filter available',()=>{
  const choices=floorChoices(capabilities,'central');
  assert.equal(floorControlVisible(choices,{axis:'floor'}),true);
  assert.equal(floorControlVisible(choices,null),true);
  assert.equal(floorControlVisible(choices,{axis:'module'}),false);
  assert.equal(floorControlVisible([{value:'all',label:'全部楼层'}],null),false);
  const view=normalizeView({module:'central',floor:'1'},capabilities);
  assert.equal(view.floor,'1');
  assert(meshVisible({module:'central',floor:1,furniture:true},view));
  assert(!meshVisible({module:'central',floor:2,designReference:true},view));
});
test('changing rooms keeps valid floors and all display switches',()=>{
  const view=normalizeView({module:'M01',floor:'2',section:true,furniture:false,glass:false,light:'dusk',camera:'top'},capabilities);
  const next=normalizeView({...view,module:'M08'},capabilities);
  assert.deepEqual(next,{...view,module:'M08'});
  assert.equal(normalizeView({...view,module:'central',floor:'3'},capabilities).floor,'3');
  assert.equal(normalizeView({...view,floor:'3'},capabilities).floor,'all');
  assert.equal(normalizeView({...view,module:'all'},capabilities).floor,'2');
});
test('whole-estate floor filters use actual available floors and hide other floors',()=>{
  const sparse=deriveCapabilities([{module:'central',floor:1},{module:'central',floor:3},{module:'M01',floor:2}]);
  assert.deepEqual(floorChoices(sparse,'all').map(c=>c.value),['all','1','2','3']);
  assert.deepEqual(floorChoices({},'all').map(c=>c.value),['all']);
  for(const floor of ['1','2','3']){
    const view=normalizeView({module:'all',floor},capabilities);
    assert.equal(view.floor,floor);
    assert(meshVisible({module:'central',floor:Number(floor),furniture:true},view));
    assert(!meshVisible({module:'central',floor:Number(floor)%3+1,furniture:true},view));
    assert.equal(normalizeView(readView(writeView(new URLSearchParams(),view)),capabilities).floor,floor);
  }
});
test('grouped house filtering excludes the central building and bedrooms',()=>{
  const view=normalizeView({module:'pods',floor:'2'},capabilities);
  assert(meshVisible({module:'M08',floor:2},view));
  assert(!meshVisible({module:'central',floor:2},view));
  assert(!meshVisible({module:'M08',floor:1},view));
});
test('grouped floors are the common available floors, not guessed levels',()=>{
  const partial=deriveCapabilities([{module:'M01',floor:1},{module:'M01',floor:2},{module:'M02',floor:1}]);
  assert.deepEqual(floorChoices(partial,'pods').map(c=>c.value),['all','1']);
});
test('refresh round trips object, floor, cut, light, overlays and camera',()=>{
  const view=normalizeView({module:'pods',floor:'2',section:true,glass:false,furniture:false,scale:false,dimensions:true,ruler:true,light:'dusk',camera:'top'},capabilities);
  const params=new URLSearchParams();writeView(params,view);
  assert.deepEqual(normalizeView(readView(params),capabilities),view);
});
test('malformed state falls back to available controls',()=>{
  const view=normalizeView(readView(new URLSearchParams('object=unknown&floor=99&light=bad&camera=bad')),capabilities);
  assert.equal(view.module,'all');assert.equal(view.floor,'all');
  assert.equal(view.light,'day');assert.equal(view.camera,'fit');
});
test('camera fitting excludes the backdrop without hiding the background',()=>{
  const view=normalizeView({},capabilities);
  assert(meshVisible({},view));
  assert(!frameable({},'PRESENTATION | backdrop',capabilities));
  assert(!frameable({module:'central',reference:true},'scale',capabilities));
  assert(frameable({module:'M01'},'terrace slab',capabilities));
});
test('selected floor measurements do not show ground-floor bedroom labels',()=>{
  const view=normalizeView({module:'M01',floor:'2'},capabilities);
  assert(!measurementVisible({module:'M01',a:[0,0,.1],b:[1,0,.1]},view,[3.09,5.8]));
  assert(measurementVisible({module:'M01',a:[0,0,3.1],b:[1,0,3.1]},view,[3.09,5.8]));
});
test('section retains the real terrace floor while hiding the outer shell',()=>{
  const view=normalizeView({module:'pods',floor:'2',section:true},capabilities);
  for(const source_name of ['ROOM • structural terrace slab','ROOM • inset terrace walking finish'])
    assert(meshVisible({module:'M01',floor:2,section_hide:true,source_name},view));
  assert(!meshVisible({module:'M01',floor:2,section_hide:true,source_name:'ROOM • outer shell'},view));
});

test('a house shell tagged on floor one still spans the actual terrace level',()=>{
  const shell={module:'M02',floor:1,designObject:'building:pod',designReference:true};
  const levels=[.1,3.1];
  assert(spansFloors(shell,.05,4.8,levels));
  const view=normalizeView({module:'M02',floor:'2',context:true},capabilities);
  assert(meshVisible({...shell,full_height:spansFloors(shell,.05,4.8,levels)},view));
  assert(!spansFloors(shell,.05,2.9,levels));
  assert(!spansFloors({...shell,floor:2},3.2,4.8,levels));
  assert(!spansFloors({...shell,designObject:'layout:terrace:M02',furniture:true},.05,4.8,levels));
  assert(!spansFloors({...shell,reference:true},.05,4.8,levels));
});

test('an explicitly floor-owned flight stays whole on its departure floor',()=>{
  const levels=[.28,4.06,6.86,9.66];
  const view={module:'central',section:false,glass:true,scale:true,furniture:true};
  for(const [floor,minimum,maximum] of [[1,.28,5.24],[2,4.28,8.04],[3,7.08,10.84]]){
    const flight={module:'central',floor,full_height:false,designObject:'building:central'};
    assert.equal(spansFloors(flight,minimum,maximum,levels),false);
    const classified={...flight,full_height:spansFloors(flight,minimum,maximum,levels)};
    assert(meshVisible(classified,{...view,floor:String(floor)}));
    assert(!meshVisible(classified,{...view,floor:String(floor+1)}));
    if(floor>1)assert(!meshVisible(classified,{...view,floor:String(floor-1)}));
  }
});
