import assert from 'node:assert/strict';
import {test} from 'node:test';
import {
  deriveCapabilities, floorChoices, objectChoices, normalizeView,
  readView, writeView, previewChoices, meshVisible, frameable, measurementVisible,
} from '../../../devtools/asset_design/web/view-state.mjs';

const records = [1,2,3,4].map(floor=>({module:'central',floor}));
for(let i=1;i<=8;i++) for(const floor of [1,2]) records.push({module:`M${String(i).padStart(2,'0')}`,floor});
const capabilities=deriveCapabilities(records);

test('preview selection contains files and images, not duplicate buildings',()=>{
  const choices=previewChoices({primaryModel:'estate.glb',models:['estate.glb','chair.glb'],images:['render.png']});
  assert.deepEqual(choices.map(c=>c.value),['model','glb:chair.glb','images']);
});
test('object selection supports the eight houses together',()=>{
  assert(objectChoices(capabilities).some(c=>c.value==='pods'));
  assert.equal(objectChoices(capabilities).filter(c=>/^M\d+$/.test(c.value)).length,8);
});
test('floors belong to the selected object',()=>{
  assert.deepEqual(floorChoices(capabilities,'all').map(c=>c.value),['all']);
  assert.deepEqual(floorChoices(capabilities,'central').map(c=>c.label),['全部楼层','一楼','二楼','三楼','屋顶']);
  assert.deepEqual(floorChoices(capabilities,'M01').map(c=>c.label),['全部楼层','一楼','二楼露台']);
  assert.deepEqual(floorChoices(capabilities,'pods').map(c=>c.value),['all','1','2']);
  assert.deepEqual(objectChoices(deriveCapabilities([])),[{value:'all',label:'完整模型'}]);
});
test('changing rooms keeps valid floors and all display switches',()=>{
  const view=normalizeView({module:'M01',floor:'2',section:true,furniture:false,glass:false,light:'dusk',camera:'top'},capabilities);
  const next=normalizeView({...view,module:'M08'},capabilities);
  assert.deepEqual(next,{...view,module:'M08'});
  assert.equal(normalizeView({...view,module:'central',floor:'3'},capabilities).floor,'3');
  assert.equal(normalizeView({...view,floor:'3'},capabilities).floor,'all');
  assert.equal(normalizeView({...view,module:'all'},capabilities).floor,'all');
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
