import test from 'node:test';
import assert from 'node:assert/strict';
import {previewImages,previewModels,cleanupCategory,cleanupCategories,filterCleanupAssets,isImageAsset,furnitureKinds,furnitureCategories,reviewModels,reviewGroups} from '../../../devtools/asset_design/web/cleanup-state.mjs';

test('furniture subcategories follow registered content, keeping complete combinations first',()=>{
  const combo={id:'elfie_furniture_kit_v16',category:'furniture',title:'第16版床桌椅组合',version:16,primaryModel:'kit/personal_nook.glb',models:['kit/bed_component.glb','kit/personal_nook.glb','kit/chair_component.glb','kit/desk_component.glb','kit/lamp_component.glb'],files:['personal_nook','bed_component','chair_component','desk_component','lamp_component'].map(n=>({path:`kit/${n}.glb`,kind:'model'}))};
  const chair={id:'image_1111111111111111',category:'furniture',title:'花瓣休闲椅',images:['chair.png'],files:[{path:'chair.png',kind:'image'}]};
  assert.deepEqual(furnitureKinds(combo),['combination','beds','seating','storage','decor']);
  assert.deepEqual(reviewModels(combo,'combination'),['kit/personal_nook.glb']);
  assert.deepEqual(reviewModels(combo,'seating'),['kit/chair_component.glb']);
  assert.deepEqual(reviewModels(combo,'all'),previewModels(combo));
  assert.deepEqual(furnitureCategories([combo,chair],'model').map(c=>c.value),['combination','beds','seating','storage','decor']);
  assert.deepEqual(furnitureCategories([combo,chair],'images').map(c=>c.value),['seating']);
  assert.equal(reviewGroups([combo,chair],'images','furniture','beds').length,0);
  assert.equal(reviewGroups([combo,chair],'model','furniture','beds')[0].assets[0].id,combo.id);
});

test('grouped lists include every matching version, newest to oldest',()=>{
  const record=(id,category,title,version)=>({id,category,title,version,models:[id+'.glb'],files:[{path:id+'.glb',kind:'model'}]});
  const assets=[record('elfie_estate_v9','estate','园区第9版',9),record('elfie_estate_v30','estate','园区第30版',30),record('elfie_second_floor_games_v1','estate','游戏布置第1版'),record('elfie_second_floor_games_v3','estate','游戏布置第3版'),record('elfie_second_floor_games_v2__central','central','主楼二楼第2版'),record('elfie_second_floor_games_v3__central','central','主楼二楼第3版')];
  const groups=reviewGroups(assets,'model','estate');
  assert.deepEqual(groups[0].assets.map(a=>a.id),['elfie_estate_v30','elfie_estate_v9']);
  assert.deepEqual(groups[1].assets.map(a=>a.id),['elfie_second_floor_games_v3','elfie_second_floor_games_v1']);
  assert.deepEqual(groups.map(group=>group.assets.length),[2,2]);
  assert.equal(groups.flatMap(group=>group.assets).length,4);
  const floors=reviewGroups(assets,'model','central');
  assert.deepEqual(floors[0].assets.map(a=>a.id),['elfie_second_floor_games_v3__central','elfie_second_floor_games_v2__central']);
  assert.deepEqual(reviewGroups([]),[]);
});

test('media and content filters use real registered previews',()=>{
  const assets=[
    {id:'elfie_estate_v2',category:'estate',models:['park.glb'],files:[{path:'park.glb',kind:'model'}]},
    {id:'elfie_second_floor_games_v3',category:'central',models:['floor.glb'],images:['ref.png'],files:[{path:'floor.glb',kind:'model'}]},
    {id:'elfie_four_person_room_v2',category:'pod',models:['room.glb'],files:[{path:'room.glb',kind:'model'}]},
    {id:'bed_v1',category:'furniture',models:['bed.glb'],images:['fabric.png'],files:[{path:'bed.glb',kind:'model'},{path:'fabric.png',kind:'texture'}]},
    {id:'image_1111111111111111',category:'concept',images:['ref.png'],files:[{path:'ref.png',kind:'image'}]},
    {id:'image_2222222222222222',category:'central',images:['floor.png'],files:[{path:'floor.png',kind:'image'}]},
    {id:'source_only',category:'pod',files:[{path:'room.blend',kind:'source'}]}
  ];
  assert.equal(cleanupCategory(assets[1]),'central');
  assert.equal(cleanupCategory(assets[2]),'rooms');
  assert.deepEqual(filterCleanupAssets(assets,'model','furniture').map(a=>a.id),['bed_v1']);
  assert.deepEqual(filterCleanupAssets(assets,'images','central').map(a=>a.id),['image_2222222222222222']);
  assert.deepEqual(filterCleanupAssets(assets,'images','all').map(a=>a.id),['image_1111111111111111','image_2222222222222222']);
  assert.equal(filterCleanupAssets(assets,'all','all').length,7);
  assert.deepEqual(cleanupCategories(assets,'images').map(c=>c.value),['central','references']);
  assert.deepEqual(cleanupCategories(assets,'model').map(c=>c.value),['estate','central','rooms','furniture']);
  assert.deepEqual(previewImages(assets[1],assets),['ref.png']);
  assert(isImageAsset(assets[4]));
  assert(!isImageAsset(assets[1]));
});

test('verified content category wins over historical version names',()=>{
  const assets=[
    {id:'elfie_ground_lounge_fixed_stair_v1',category:'estate'},
    {id:'elfie_second_floor_games_v3',category:'estate'},
    {id:'elfie_upper_activity_rooms_v1',category:'estate'},
    {id:'elfie_upper_activity_rooms_v1__furniture',category:'furniture'},
    {id:'checkpoint_2026-10-03_approved_v8__pod',category:'pod'},
    {id:'elfie_four_person_room_v2',category:'pod'}
  ];
  assert.deepEqual(assets.map(cleanupCategory),['estate','estate','estate','furniture','rooms','rooms']);
});

test('model previews include only this asset’s registered models',()=>{
  const asset={id:'room_v1',primaryModel:'missing.glb',models:['room/main.glb','other.glb'],files:[
    {path:'room/main.glb',kind:'model'},{path:'room/part.glb',kind:'model'},
    {path:'room/source.blend',kind:'source'}
  ]};
  assert.deepEqual(previewModels(asset),['room/main.glb','room/part.glb']);
  assert.deepEqual(previewModels({files:[]}),[]);
});

test('only saved registered images become previews, never textures or unknown paths',()=>{
  const asset={thumbnail:'missing.png',images:['texture.png','render.png'],files:[
    {path:'texture.png',kind:'texture'},{path:'render.png',kind:'image'}
  ]};
  assert.deepEqual(previewImages(asset),['render.png']);
  assert.deepEqual(previewImages({models:['room.glb'],files:[]}),[]);
});
