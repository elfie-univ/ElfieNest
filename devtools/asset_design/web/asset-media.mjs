import {cleanupCategories,furnitureCategories,reviewGroups,reviewModels,previewModels,isImageAsset} from './cleanup-state.mjs';

export const imageKinds = {all: '全部图片', reference: '设计参考', render: '模型截图', layout: '布局尺寸', history: '对比资料'};
export const mediaModes = [{value:'model',label:'三维模型'},{value:'images',label:'图片'},{value:'compare',label:'对照'}];

export function storageInventory(assets) {
  const versions=new Map(assets.map(a=>[a.id,a])),files=new Map();
  for(const asset of versions.values())for(const file of asset.files||[])files.set(file.path,file);
  const rows=[...files.values()];
  return {versions:versions.size,files:files.size,
    bytes:rows.every(f=>Number.isFinite(f.bytes)&&f.bytes>=0)?rows.reduce((sum,f)=>sum+f.bytes,0):null};
}

export function workbenchMenus(catalog,mode='model',requestedCategory='',requestedFurniture='',assetId='') {
  const eligible=catalog.assets.filter(a=>assetModes(a,catalog).some(m=>m.value===mode)
    &&(mode!=='images'||previewModels(a).length===0));
  const media=mode==='images'?'images':'model';
  const categories=cleanupCategories(eligible,media);
  const category=categories.some(c=>c.value===requestedCategory)?requestedCategory:categories[0]?.value||'';
  const allFurniture=furnitureCategories(eligible,media);
  const furnitureChoices=category==='furniture'?allFurniture:[];
  const furniture=furnitureChoices.some(c=>c.value===requestedFurniture)?requestedFurniture:furnitureChoices[0]?.value||'all';
  let groups=category?reviewGroups(eligible,media,category,furniture):[];
  if(category==='estate'&&media==='model'){
    const order=new Map(catalog.assets.map((a,index)=>[a.id,index]));
    const number=a=>Number(a.title.match(/^V(\d+)\s*·/)?.[1]||0);
    const assets=groups.flatMap(g=>g.assets).sort((a,b)=>number(b)-number(a)||order.get(b.id)-order.get(a.id));
    groups=assets.length?[{key:'complete-estate',label:'完整园区',assets}]:[];
  }
  const available=groups.flatMap(g=>g.assets);
  const selected=available.find(a=>a.id===assetId)||available.find(a=>/·\s*已确认$/.test(a.title))||groups[0]?.assets[0]||null;
  const contentGroups=[
    {label:'内容分类',choices:categories.filter(c=>c.value!=='furniture')},
    {label:'家具',choices:allFurniture.map(c=>({...c,value:'furniture:'+c.value,label:'家具 · '+c.label}))},
  ].filter(g=>g.choices.length);
  return {categories,category,contentGroups,furnitureChoices,furniture,groups,selected,models:selected?reviewModels(selected,furniture):[]};
}

export function assetDeleteState(asset,busy=false) {
  const picture=asset&&isImageAsset(asset);
  return {disabled:busy||!asset,label:busy?'正在删除…':picture?'删除当前图片':'删除当前版本',
    scope:picture?'直接删除当前图片；保留共享文件与可恢复备份。':'直接删除整个保存版本（含部件）；保留共享文件、构建输入与可恢复备份。'};
}

export function nextVersionAfterDeletion(groups,id) {
  const group=groups.find(g=>g.assets.some(a=>a.id===id));
  const index=group?.assets.findIndex(a=>a.id===id)??-1;
  return group?.assets[index+1]?.id||group?.assets[index-1]?.id||'';
}

export function versionNavigation(groups,id,busy=false) {
  const ids=groups.flatMap(g=>g.assets.map(a=>a.id)),index=ids.indexOf(id);
  if(busy||index<0)return {newer:'',older:'',latest:''};
  return {newer:ids[index-1]||'',older:ids[index+1]||'',latest:index>0?ids[0]:''};
}

export function versionShortcut(event) {
  if(event.defaultPrevented||event.repeat||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey)return '';
  if(!event.target?.closest?.('.version-navigation')&&event.target?.closest?.('input,select,textarea,button,a,iframe,summary,[contenteditable]:not([contenteditable="false"]),[role="combobox"],[role="slider"],[role="menu"]'))return '';
  return event.key==='ArrowLeft'?'newer':event.key==='ArrowRight'?'older':'';
}

export function assetModes(asset,catalog) {
  const model=asset.primaryModel||asset.models?.[0];
  const hasModel=!!model&&(asset.files||[]).some(f=>f.kind==='model'&&f.path===model);
  const registered=new Set(catalog.assets.flatMap(a=>(a.files||[]).filter(f=>f.kind==='image').map(f=>f.path)));
  const images=imageEntries(asset,catalog).filter(e=>registered.has(e.path));
  return mediaModes.filter(m=>m.value==='model'?hasModel:m.value==='images'?images.length
    :hasModel&&images.some(e=>e.kind==='reference'));
}

export function metadataReferences(asset,metadata,catalog) {
  const registered=catalog.assets.flatMap(a=>(a.files||[]).filter(f=>f.kind==='image').map(f=>f.path));
  const own=(asset.files||[]).filter(f=>f.kind==='image').map(f=>f.path);
  const references=[];
  for(const value of [metadata.reference_image,metadata.reference]){
    if(typeof value!=='string'||value.includes('://')||!(/\.(png|jpe?g|webp|svg)$/i).test(value))continue;
    if(registered.includes(value)){if(!references.includes(value))references.push(value);continue;}
    const matchesPath=p=>value.includes('/')?p.endsWith('/'+value):p.split('/').pop()===value;
    const local=own.filter(matchesPath);
    const global=registered.filter(matchesPath);
    const matches=local.length?local:global;
    if(matches.length===1&&!references.includes(matches[0]))references.push(matches[0]);
  }
  return references;
}

export function imageEntries(asset, catalog) {
  const entries = new Map();
  const registered = new Set(catalog.assets.flatMap(a => (a.files || []).filter(f => f.kind === 'image').map(f => f.path)));
  for (const path of asset.images || []) {
    if (/(^|\/)(textures?|materials?)\//i.test(path) || /(?:_normal|_roughness|_metallic|_color|_albedo)\.(png|jpe?g)$/i.test(path)) continue;
    const name = path.split('/').pop();
    const kind = /compar|overlay|before|after|regions/i.test(name) ? 'history'
      : isImageAsset(asset) || asset.id === 'design_references' || /concept/i.test(name)
        || /^(reference(?:_floor_\d+)?|pod_reference|petal_chair_reference|bed_desk_clean_structure)\.(png|jpe?g|webp|svg)$/i.test(name) ? 'reference'
      : /plan|layout|dimension|measure|budget|outline/i.test(name) ? 'layout' : 'render';
    entries.set(path, {path, name, kind});
  }
  for(const path of asset.referenceImages||[]){
    if(registered.has(path))entries.set(path,{path,name:path.split('/').pop(),kind:'reference'});
  }
  // Existing floor references describe the central building, not similarly numbered house floors.
  for (const [floor, path] of Object.entries(asset.referenceFloors || {})) {
    if (!registered.has(path) && !(asset.images || []).includes(path)) continue;
    entries.set(path, {path, name: `主楼 ${floor} 楼参考`, kind: 'reference', module: 'central', floor});
  }
  return [...entries.values()];
}

export function referenceFor(entries, view) {
  const exact=entries.find(e=>e.kind==='reference'&&e.module===view.module&&e.floor===view.floor);
  if(exact)return exact;
  const unscoped=entries.filter(e=>e.kind==='reference'&&!e.module);
  return view.module==='all'&&view.floor==='all'&&unscoped.length===1?unscoped[0]:undefined;
}
