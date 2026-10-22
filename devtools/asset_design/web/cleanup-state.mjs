// Filter registered previews and review records without changing the catalogue.
export function previewImages(asset,assets=[asset]) {
  const registered=new Set(assets.flatMap(a=>(a.files||[]).filter(f=>f.kind==='image').map(f=>f.path)));
  return [...new Set([asset.thumbnail,...(asset.images||[])])].filter(path=>registered.has(path));
}
export function previewModels(asset) {
  const registered=(asset.files||[]).filter(file=>file.kind==='model'&&/\.(glb|gltf)$/i.test(file.path)).map(file=>file.path);
  return [...new Set([asset.primaryModel,...(asset.models||[]),...registered])].filter(path=>registered.includes(path));
}
export const cleanupCategoryLabels={estate:'整体园区',central:'主楼空间',rooms:'小屋房间',furniture:'家具组件',references:'效果与参考图',review:'审阅资料',other:'其他资产'};
export function isImageAsset(asset) {
  return /^image_[a-f0-9]{16}$/.test(asset.id||'')&&previewModels(asset).length===0;
}
export function cleanupCategory(asset) {
  return ({estate:'estate',central:'central',pod:'rooms',room:'rooms',early:'rooms',furniture:'furniture',concept:'references',reference:'references',review:'review'})[asset.category]||'other';
}
export function filterCleanupAssets(assets,media='all',category='all') {
  return assets.filter(asset=>(category==='all'||cleanupCategory(asset)===category)
    &&(media==='all'||media==='model'&&previewModels(asset).length>0||media==='images'&&isImageAsset(asset)&&previewImages(asset,assets).length>0));
}
export function cleanupCategories(assets,media='all') {
  const eligible=filterCleanupAssets(assets,media);
  return Object.entries(cleanupCategoryLabels).map(([value,label])=>({value,label,count:eligible.filter(a=>cleanupCategory(a)===value).length})).filter(c=>c.count);
}
export const furnitureCategoryLabels={combination:'家具组合',beds:'床与床品',seating:'沙发与座椅',storage:'桌柜与收纳',decor:'灯具与装饰',entertainment:'娱乐设备'};
function furnitureModelKind(path) {
  const name=path.split('/').pop();
  if(/^(bed_|bedding_|sheet_|pillow_)/i.test(name))return 'beds';
  if(/chair_|sofa_|bench_|pouf_/i.test(name))return 'seating';
  if(/desk_|cabinet_|bookcase_/i.test(name))return 'storage';
  if(/lamp_|lights|rug_|plush_|desktop_details/i.test(name))return 'decor';
  if(/television|console|piano|game_machine/i.test(name))return 'entertainment';
  return 'combination';
}
export function furnitureKinds(asset) {
  if(cleanupCategory(asset)!=='furniture')return [];
  const kinds=new Set(previewModels(asset).map(furnitureModelKind));
  if(isImageAsset(asset)){
    const title=asset.title||'';
    kinds.add(/床.*桌|床桌|分件|组合/.test(title)?'combination'
      :/椅|沙发|坐墩/.test(title)?'seating':/床|被|枕/.test(title)?'beds'
      :/桌|柜/.test(title)?'storage':/电视|游戏机|乐器/.test(title)?'entertainment':'decor');
  }
  return Object.keys(furnitureCategoryLabels).filter(key=>kinds.has(key));
}
export function reviewModels(asset,kind='all') {
  return previewModels(asset).filter(path=>kind==='all'||cleanupCategory(asset)!=='furniture'||furnitureModelKind(path)===kind);
}
export function furnitureCategories(assets,media='model') {
  const eligible=filterCleanupAssets(assets,media,'furniture');
  return Object.entries(furnitureCategoryLabels).map(([value,label])=>({value,label,count:eligible.filter(a=>furnitureKinds(a).includes(value)).length})).filter(c=>c.count);
}
const seriesLabels={elfie_estate:'完整园区 · 建筑方案',checkpoint_2026_10_03_approved:'建筑保留快照',
  elfie_estate_room_v5:'园区 · M01 四人房布置',elfie_estate_all_rooms:'园区 · 八间四人房布置',
  elfie_central_furnished:'主楼三层布置',elfie_upper_activity_rooms:'八个露台活动布置',
  elfie_ground_lounge_fixed_stair:'主楼一楼客厅布置',elfie_second_floor_games:'主楼二楼游戏布置',
  elfie_pod:'独立小屋建筑',elfie_four_person_room:'M01 四人房布置',
  elfie_furniture_kit:'床桌椅组合',elfie_bed_shell:'独立床壳'};
function reviewSeries(asset) {
  if(isImageAsset(asset))return 'images:'+cleanupCategory(asset);
  const id=asset.id.split('__')[0];
  if(/^elfie_furniture_v\d+_/.test(id))return 'elfie_furniture_kit';
  return id.replace(/_v\d+$/,'').replaceAll('-','_');
}
function reviewVersion(asset) {
  return Number(asset.title?.match(/^V(\d+)\s*·/)?.[1]??asset.version??asset.id.match(/^elfie_furniture_v(\d+)_/)?.[1]??asset.id.split('__')[0].match(/_v(\d+)$/)?.[1]??0);
}
export function reviewGroups(assets,media='model',category='estate',kind='all') {
  const groups=new Map();
  for(const asset of filterCleanupAssets(assets,media,category)){
    if(category==='furniture'&&kind!=='all'&&!furnitureKinds(asset).includes(kind))continue;
    const key=reviewSeries(asset);
    if(!groups.has(key))groups.set(key,{key,label:seriesLabels[key]||(isImageAsset(asset)?cleanupCategoryLabels[cleanupCategory(asset)]+' · 图片方案':asset.title),assets:[]});
    groups.get(key).assets.push(asset);
  }
  const order=new Map(assets.map((asset,index)=>[asset.id,index]));
  const priority=key=>['elfie_estate','elfie_furniture_kit','elfie_pod'].includes(key)?0:1;
  return [...groups.values()].map(group=>{
    group.assets.sort((a,b)=>reviewVersion(b)-reviewVersion(a)||order.get(b.id)-order.get(a.id));
    return group;
  }).sort((a,b)=>priority(a.key)-priority(b.key));
}
