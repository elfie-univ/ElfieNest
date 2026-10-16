import assert from 'node:assert/strict';
import {test} from 'node:test';
import {imageEntries, referenceFor, assetModes, metadataReferences,workbenchMenus,assetDeleteState,nextVersionAfterDeletion,storageInventory,versionNavigation,versionShortcut} from '../../../devtools/asset_design/web/asset-media.mjs';

test('version navigation follows the current menu, with no wrapping or stale targets',()=>{
  const groups=[{assets:[{id:'v3'},{id:'v2'}]},{assets:[{id:'v1'}]}];
  assert.deepEqual(versionNavigation(groups,'v2'),{newer:'v3',older:'v1',latest:'v3'});
  assert.deepEqual(versionNavigation(groups,'v3'),{newer:'',older:'v2',latest:''});
  assert.deepEqual(versionNavigation(groups,'v1'),{newer:'v2',older:'',latest:'v3'});
  for(const [rows,id,busy] of [[groups,'unknown',false],[groups,'v2',true],[[],'v2',false],[[{assets:[{id:'only'}]}],'only',false]]){
    assert.deepEqual(versionNavigation(rows,id,busy),{newer:'',older:'',latest:''});
  }
});

test('arrow shortcuts leave typing, menus, preview controls and modified keys alone',()=>{
  const event={key:'ArrowLeft',target:{closest:()=>null}};
  assert.equal(versionShortcut(event),'newer');
  assert.equal(versionShortcut({...event,key:'ArrowRight'}),'older');
  assert.equal(versionShortcut({...event,key:'ArrowUp'}),'');
  for(const flag of ['altKey','ctrlKey','metaKey','shiftKey','repeat','defaultPrevented'])assert.equal(versionShortcut({...event,[flag]:true}),'');
  for(const tag of ['input','select','textarea','button','a','iframe','contenteditable']){
    assert.equal(versionShortcut({...event,target:{closest:selector=>selector==='.version-navigation'?null:{tagName:tag}}}),'');
  }
  assert.equal(versionShortcut({...event,key:'ArrowRight',target:{closest:()=>({})}}),'older');
});

test('storage inventory counts saved versions and unique physical paths, including source and support files',()=>{
  const a={id:'a',files:[{path:'a.glb',bytes:100},{path:'shared.png',bytes:20},{path:'a.blend',bytes:200}]};
  const b={id:'b',files:[{path:'b.glb',bytes:50},{path:'shared.png',bytes:20},{path:'build.json',bytes:10}]};
  assert.deepEqual(storageInventory([a,b,a]),{versions:2,files:5,bytes:380});
  assert.deepEqual(storageInventory([a]),{versions:1,files:3,bytes:320});
  assert.deepEqual(storageInventory([]),{versions:0,files:0,bytes:0});
  assert.deepEqual(storageInventory([{id:'unknown',files:[{path:'missing-size.glb'}]}]),{versions:1,files:1,bytes:null});
});

test('category inventory follows the selectable mode and furniture subtype after deletion',()=>{
  const make=(id,models,images=[])=>({id,title:id,category:'furniture',primaryModel:models[0],models,images,
    files:[...models.map(path=>({path,kind:'model',bytes:100})),...images.map(path=>({path,kind:'image',bytes:20}))]});
  const kit=make('elfie_furniture_kit_v1',['kit/bed_component.glb','kit/chair_component.glb']);
  const chair=make('chair_v1',['chair/chair_component.glb']);
  const image=make('image_1111111111111111',[],['chair.png']);
  const inventory=(assets,mode,kind)=>storageInventory(workbenchMenus({assets},mode,'furniture',kind).groups.flatMap(g=>g.assets));
  assert.deepEqual(inventory([kit,chair,image],'model','beds'),{versions:1,files:2,bytes:200});
  assert.deepEqual(inventory([kit,chair,image],'model','seating'),{versions:2,files:3,bytes:300});
  assert.deepEqual(inventory([kit,image],'model','seating'),{versions:1,files:2,bytes:200});
  assert.deepEqual(inventory([kit,chair,image],'images','decor'),{versions:1,files:1,bytes:20});
});

test('workbench menus share content/furniture categories and restrict versions by media',()=>{
  const make=(id,category,title,models,images=[])=>({id,category,title,primaryModel:models[0],models,images,files:[...models.map(path=>({path,kind:'model'})),...images.map(path=>({path,kind:'image'}))]});
  const kit=make('elfie_furniture_kit_v16','furniture','床桌椅第16版',['kit/personal_nook.glb','kit/bed_component.glb','kit/chair_component.glb'],['kit/reference.png']);
  const old=make('elfie_furniture_kit_v13','furniture','床桌椅第13版',['old/personal_nook.glb','old/chair_component.glb']);
  const picture=make('image_1111111111111111','furniture','花瓣椅',[],['chair.png']);
  const park=make('elfie_estate_v30','estate','完整园区第30版',['park.glb']);
  const catalog={assets:[kit,old,picture,park]};
  const furniture=workbenchMenus(catalog,'model','furniture','seating');
  assert.equal(furniture.category,'furniture');
  assert.equal(furniture.furniture,'seating');
  assert.deepEqual(furniture.categories.map(c=>c.value),['estate','furniture']);
  assert.deepEqual(furniture.contentGroups.map(g=>g.label),['内容分类','家具']);
  assert.deepEqual(furniture.contentGroups[1].choices.map(c=>c.value),['furniture:combination','furniture:beds','furniture:seating']);
  assert.deepEqual(furniture.groups[0].assets.map(a=>a.id),[kit.id,old.id]);
  assert.equal(furniture.selected.id,kit.id);
  assert.deepEqual(furniture.models,['kit/chair_component.glb']);
  assert.equal(workbenchMenus(catalog,'model','furniture','seating',old.id).selected.id,old.id);
  const pictures=workbenchMenus(catalog,'images','furniture','seating',kit.id);
  assert.deepEqual(pictures.groups.flatMap(g=>g.assets).map(a=>a.id),[picture.id]);
  assert.equal(pictures.selected.id,picture.id);
  const compare=workbenchMenus(catalog,'compare','furniture','seating',old.id);
  assert.deepEqual(compare.groups.flatMap(g=>g.assets).map(a=>a.id),[kit.id]);
  assert.equal(compare.selected.id,kit.id);
  assert.equal(workbenchMenus(catalog,'model','furniture','decor').furniture,'combination');
  const empty=workbenchMenus({assets:[]},'model','estate');
  assert.equal(empty.selected,null);assert.deepEqual(empty.groups,[]);assert.deepEqual(empty.models,[]);
});

test('direct deletion identifies its scope and blocks repeated clicks while busy',()=>{
  const model={id:'kit_v13',models:['kit.glb','bed.glb'],files:[{path:'kit.glb',kind:'model'},{path:'bed.glb',kind:'model'}]};
  const picture={id:'image_1111111111111111',models:[],files:[]};
  assert.equal(assetDeleteState(model).label,'删除当前版本');
  assert.match(assetDeleteState(model).scope,/整个保存版本/);
  assert.equal(assetDeleteState(picture).label,'删除当前图片');
  assert.match(assetDeleteState(picture).scope,/当前图片/);
  assert(assetDeleteState(model,true).disabled);
  assert(assetDeleteState(null).disabled);
  assert.equal(assetDeleteState(model).disabled,false);
});
test('deleting a version selects the next older version in the same group first',()=>{
  const groups=[{assets:[{id:'v3'},{id:'v2'},{id:'v1'}]},{assets:[{id:'other'}]}];
  assert.equal(nextVersionAfterDeletion(groups,'v3'),'v2');
  assert.equal(nextVersionAfterDeletion(groups,'v2'),'v1');
  assert.equal(nextVersionAfterDeletion(groups,'v1'),'v2');
  assert.equal(nextVersionAfterDeletion([{assets:[{id:'only'}]}],'only'),'');
});
test('whole-estate menus prefer later furniture integrations over high-numbered building samples',()=>{
  const make=(id,title)=>({id,title,category:'estate',models:[id+'.glb'],primaryModel:id+'.glb',files:[{path:id+'.glb',kind:'model'}]});
  const sample=make('elfie_estate_v30','四人小窝样板');
  const lounge=make('elfie_ground_lounge_fixed_stair_v1','一楼沿楼梯客厅');
  const games=make('elfie_second_floor_games_v3','二楼活动家具校正版');
  const catalog={assets:[sample,lounge,games]};
  const menu=workbenchMenus(catalog,'model','estate');
  assert.equal(menu.selected.id,games.id);
  assert.equal(menu.groups.length,1);
  assert.equal(menu.groups[0].label,'完整园区');
  assert.equal(workbenchMenus(catalog,'model','estate','',sample.id).selected.id,sample.id);
  assert.equal(workbenchMenus({assets:[sample,lounge]},'model','estate').selected.id,lounge.id);
});

test('numbered estate revisions form one group without renumbering gaps or switching an explicit selection',()=>{
  const make=(id,title)=>({id,title,category:'estate',primaryModel:id+'.glb',models:[id+'.glb'],files:[{path:id+'.glb',kind:'model'}]});
  const old=make('elfie_estate_v28','V028 · 10-06 09:07 · 四人小窝样板 · 待确认');
  const confirmed=make('elfie_second_floor_games_v3','V038 · 10-12 16:07 · 二楼家具比例校正 · 已确认');
  const latest=make('elfie_estate_eight_rooms_optimized_v1','V039 · 10-14 08:37 · 窗框收口修复 · 待确认');
  const catalog={assets:[old,confirmed,latest]};
  const menu=workbenchMenus(catalog,'model','estate');
  assert.equal(menu.groups.length,1);
  assert.deepEqual(menu.groups[0].assets.map(a=>a.id),[latest.id,confirmed.id,old.id]);
  assert.equal(menu.selected.id,confirmed.id);
  assert.equal(workbenchMenus(catalog,'model','estate','',old.id).selected.id,old.id);
  const after=workbenchMenus({assets:[old,latest]},'model','estate');
  assert.deepEqual(after.groups[0].assets.map(a=>a.title.split(' · ')[0]),['V039','V028']);
  assert.equal(old.title,'V028 · 10-06 09:07 · 四人小窝样板 · 待确认');
});

test('confirmed default is limited to eligible content and never overrides a bookmarked pending version',()=>{
  const make=(id,title,reference=false)=>({id,title,category:'furniture',primaryModel:id+'/personal_nook.glb',models:[id+'/personal_nook.glb'],images:reference?[id+'/reference.png']:[],files:[{path:id+'/personal_nook.glb',kind:'model'},...(reference?[{path:id+'/reference.png',kind:'image'}]:[])]});
  const approved=make('elfie_furniture_kit_v29','V031 · 10-13 17:44 · 纯色存储优化 · 已确认');
  const pending=make('elfie_furniture_kit_v30','V032 · 10-13 20:20 · 灯槽内衬修复 · 待确认',true);
  const catalog={assets:[approved,pending]};
  assert.equal(workbenchMenus(catalog,'model','furniture','combination').selected.id,approved.id);
  assert.equal(workbenchMenus(catalog,'model','furniture','combination',pending.id).selected.id,pending.id);
  assert.equal(workbenchMenus(catalog,'compare','furniture','combination').selected.id,pending.id);
});

const asset={id:'room',category:'estate',title:'客厅',description:'沿墙布置',images:[
  'room/reference.png','room/01_living_3d.png','room/02_plan.png',
  'room/before_front.png','room/textures/linen_color.png',
],referenceFloors:{'1':'room/reference.png','2':'other/reference_floor_2.png'},files:[],models:[]};
const catalog={assets:[asset,{id:'other',files:[{path:'other/reference_floor_2.png',kind:'image'}]}]};
test('gallery separates reference, model screenshots, layout and comparisons, omitting textures',()=>{
  const entries=imageEntries(asset,catalog);
  assert.deepEqual(entries.map(e=>e.kind),['reference','render','layout','history','reference']);
  assert(!entries.some(e=>e.path.includes('textures')));
});
test('floor references are for the central building, never a house terrace',()=>{
  const entries=imageEntries(asset,catalog);
  assert.equal(referenceFor(entries,{module:'central',floor:'2'})?.path,'other/reference_floor_2.png');
  assert.equal(referenceFor(entries,{module:'pods',floor:'2'}),undefined);
  assert.equal(referenceFor(entries,{module:'M01',floor:'1'}),undefined);
  assert.equal(referenceFor(entries,{module:'all',floor:'all'}),undefined);
});
test('unregistered reference paths cannot become automatic references',()=>{
  const entries=imageEntries({...asset,referenceFloors:{'3':'private.png'}},catalog);
  assert(!entries.some(e=>e.path==='private.png'));
});

test('media modes exclude image-only models, missing references and material textures',()=>{
  const make=(id,models,images)=>({id,category:'furniture',title:id,models,images,primaryModel:models[0],
    files:[...models.map(path=>({path,kind:'model'})),...images.map(path=>({path,kind:'image'}))]});
  const model=make('model', ['model.glb'], []);
  const pictures=make('pictures', [], ['reference.png']);
  const rendered=make('rendered', ['rendered.glb'], ['render.png','reference_comparison.png',
    '01_bedroom_reference.jpg','01_reference_direction.png','02_bed_reference.png']);
  const compare=make('compare', ['compare.glb'], ['compare/reference.png']);
  const materials=make('materials', ['materials.glb'], ['textures/linen_color.png']);
  const missing=make('missing', ['missing.glb'], []);missing.files=[];
  const catalog={assets:[model,pictures,rendered,compare,materials,missing]};
  const modes=a=>assetModes(a,catalog).map(m=>m.value);
  assert.deepEqual(modes(model),['model']);
  assert.deepEqual(modes(pictures),['images']);
  assert.deepEqual(modes(rendered),['model','images']);
  assert.deepEqual(modes(compare),['model','images','compare']);
  assert.deepEqual(modes(materials),['model']);
  assert.deepEqual(modes(missing),[]);
});

test('one unscoped asset reference can be compared with the whole model, without claiming a floor match',()=>{
  const reference={path:'reference.png',kind:'reference'};
  assert.equal(referenceFor([reference],{module:'all',floor:'all'}),reference);
  assert.equal(referenceFor([reference],{module:'M01',floor:'2'}),undefined);
  assert.equal(referenceFor([reference,{...reference,path:'other.png'}],{module:'all',floor:'all'}),undefined);
});

test('saved metadata links only registered local reference images, never arbitrary files or ambiguous names',()=>{
  const asset={files:[{path:'room/reference.png',kind:'image'}]};
  const catalog={assets:[asset,{files:[{path:'shared/original.png',kind:'image'},{path:'other/reference.png',kind:'image'}]}]};
  assert.deepEqual(metadataReferences(asset,{reference:'reference.png'},catalog),['room/reference.png']);
  assert.deepEqual(metadataReferences(asset,{reference:'other/reference.png'},catalog),['other/reference.png']);
  assert.deepEqual(metadataReferences(asset,{reference_image:'original.png'},catalog),['shared/original.png']);
  assert.deepEqual(metadataReferences({files:[]},{reference:'reference.png'},catalog),[]);
  assert.deepEqual(metadataReferences(asset,{reference:'private.png'},catalog),[]);
  assert.deepEqual(metadataReferences(asset,{reference:'other.glb'},catalog),[]);
  assert.deepEqual(metadataReferences(asset,{reference:'https://example.com/reference.png'},catalog),[]);
  const model={id:'room',category:'furniture',title:'Room',primaryModel:'room.glb',models:['room.glb'],images:[],
    files:[{path:'room.glb',kind:'model'},...asset.files],referenceImages:metadataReferences(asset,{reference_image:'original.png'},catalog)};
  assert.deepEqual(assetModes(model,{assets:[model,...catalog.assets]}).map(m=>m.value),['model','images','compare']);
});
