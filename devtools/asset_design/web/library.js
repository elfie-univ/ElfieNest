import {objectImages} from '/assets/design/content-images.mjs';
import {confirmedReferenceSignature,designMenu,contentMenuTree,adoptionLabel,versionRemovalScope,filePreviewSelection,publishedPreview} from '/assets/design/design-state.mjs';
import {readView,writeView,normalizeView,defaultView} from '/assets/design/view-state.mjs';
import {readCatalog} from '/assets/design/catalog-request.mjs';
import {imageEntries,imageKinds,referenceFor,assetModes,mediaModes,metadataReferences,workbenchMenus,assetDeleteState,nextVersionAfterDeletion,storageInventory,versionNavigation,versionShortcut} from '/assets/design/asset-media.mjs';
const initialCatalog=await readCatalog();
let catalog=initialCatalog.catalog,catalogEtag=initialCatalog.etag;
let catalogSignature=JSON.stringify(catalog);
async function readDesignIndex(){const r=await fetch('/assets/design/design/index',{cache:'no-store'});if(!r.ok)throw new Error('对象目录无法读取');return r.json();}
let designIndex=await readDesignIndex();
const kindLabels={model:'模型',source:'Blender 源文件',image:'图片与贴图',data:'尺寸／数据',support:'构建与辅助文件',all:'全部文件'};
const el=id=>document.getElementById(id),url=p=>'/assets/design/files/'+p.split('/').map(encodeURIComponent).join('/');
async function readReferences(current){await Promise.all(current.assets.map(async asset=>{
 const metadata=asset.files.find(f=>f.kind==='data'&&f.path.split('/').pop()==='metadata.json');
 if(!metadata)return;
 const response=await fetch(url(metadata.path));if(!response.ok)throw new Error('资产元数据无法读取：'+asset.title);
 asset.referenceImages=metadataReferences(asset,await response.json(),current);
}));}
await readReferences(catalog);
const size=n=>!Number.isFinite(n)?'大小未记录':n>=1024**3?(n/1024**3).toFixed(2)+' GB':n>=1024**2?(n/1024**2).toFixed(1)+' MB':n>=1024?(n/1024).toFixed(1)+' KB':n+' B';
const initial=new URLSearchParams(location.hash.slice(1)),frame=el('viewer');
const requestedMode=initial.get('view');
let mode=mediaModes.some(m=>m.value===requestedMode)?requestedMode:'model';
let category=initial.get('category')||'',furniture=initial.get('furnitureCategory')||'',groups=[];
let asset=null,modelFile='',fileKind='model',imageKind='all',imagePath='',manualReference='';
let deleteBusy=false,deleteMessage='',catalogStale=false,confirmBusy=false,loadedPlan=null,pendingDelete=null;
let designObject=initial.get('designObject')||'',designVersion=initial.get('revision')||'';
let exteriorPreview=initial.get('exterior')==='1';
const rememberedVersions=new Map();
let modelStats=null,imageDimensions='',rawPreview=false;
let view=readView(initial),capabilities={},entries=[];
let refreshBusy=false,refreshTimer=null,pendingOrbit=null;
async function refreshCatalog(){
 if(refreshBusy||document.hidden||deleteBusy||confirmBusy||pendingDelete||catalogStale)return;
 refreshBusy=true;
 try{
  const pending=await readCatalog(catalogEtag);
  if(!pending||JSON.stringify(pending.catalog)===catalogSignature){
   if(pending)catalogEtag=pending.etag;
   if(frame.dataset.ready!=='yes')return;
   const index=await readDesignIndex();
   const ownDraft=data=>JSON.stringify(data.objects.find(o=>o.id===designObject)?.versions.filter(v=>v.draft).map(v=>[v.digest,v.contentDigest]));
   const changed=confirmedReferenceSignature(index,designObject,loadedPlan)!==confirmedReferenceSignature(designIndex,designObject,loadedPlan)||designVersion==='draft'&&ownDraft(index)!==ownDraft(designIndex);
   if(changed){
    const orbit=frame.contentWindow.elfiePreview?.orbit?.();
    designIndex=index;frame.dataset.source='';chooseFromMenus();pendingOrbit=orbit;
   }
   return;
  }
  const updated=pending.catalog;
  const signature=JSON.stringify(updated);
  const index=await readDesignIndex();
  // A publication may still be completing. Retry without consuming its new ID.
  const known=new Set(catalog.assets.map(a=>a.id));
  if(updated.assets.some(a=>!known.has(a.id)&&a.designObject&&!index.objects.some(o=>o.id===a.designObject.id&&o.versions.some(v=>v.id===a.designVersion?.id))))return;
  await readReferences(updated);
  if(deleteBusy||confirmBusy||pendingDelete||catalogStale)return;
  const next=publishedPreview(catalog,updated,index,designObject,view);
  const orbit=next&&frame.dataset.ready==='yes'?frame.contentWindow.elfiePreview?.orbit?.():null;
  catalog=updated;designIndex=index;catalogSignature=signature;catalogEtag=pending.etag;
  const params=new URLSearchParams(location.hash.slice(1));
  if(next){
   designObject=next.object;designVersion=next.version;
   params.delete('file');params.delete('image');
  }
  renderStats();chooseFromMenus(params);if(next)pendingOrbit=orbit;
 }catch(error){
  // Keep the last usable catalogue and retry after service restarts or read failures.
  console.warn('资产目录自动更新暂未成功：',error.message);
 }finally{refreshBusy=false;}
}
function scheduleCatalogRefresh(){
 clearTimeout(refreshTimer);
 refreshTimer=setTimeout(async()=>{await refreshCatalog();scheduleCatalogRefresh();},2000);
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden){refreshCatalog();scheduleCatalogRefresh();}});
window.addEventListener('focus',()=>refreshCatalog());
function gallery(){return entries.filter(e=>imageKind==='all'||e.kind===imageKind);}
function updateHash(){
 const params=new URLSearchParams({category,view:mode});if(asset)params.set('asset',asset.id);writeView(params,view);
 if(exteriorPreview)params.set('exterior','1');
 if(category==='furniture')params.set('furnitureCategory',furniture);
 if(asset?.designObject){params.set('designObject',asset.designObject);params.set('revision',asset.designVersion);}
 if(asset&&modelFile&&(rawPreview||modelFile!==(asset.primaryModel||asset.models[0])))params.set('file',modelFile);
 if(imageKind!=='all')params.set('imageKind',imageKind);
 if(imagePath)params.set('image',imagePath);
 if(manualReference)params.set('reference',manualReference);
 history.replaceState(null,'','#'+params);
}
function renderDeleteAction(){
 const state=assetDeleteState(asset,deleteBusy),button=el('deleteAsset');
 const scope=versionRemovalScope(designIndex,asset?.id),live=['live','draft'].includes(asset?.designVersion);
 button.hidden=mode==='images'||!!live;
 button.disabled=state.disabled||confirmBusy||catalogStale||scope.protected;button.textContent=state.label;
 button.title=scope.protected?'当前对象的确认版，保留此版本':state.scope+(scope.labels.length?'\n关联对象：'+scope.labels.join('、'):'');
 button.setAttribute('aria-label',state.label+(asset?'：'+asset.title:''));
 el('deleteStatus').textContent=deleteMessage;
 el('deletePrompt').hidden=!pendingDelete;
 el('deleteConfirm').disabled=deleteBusy||confirmBusy;el('deleteCancel').disabled=deleteBusy;
 renderVersionNavigation();renderConfirmation();
}
function renderVersionNavigation(){
 const targets=versionNavigation(groups,mode!=='images'?designVersion:asset?.id,deleteBusy||confirmBusy||catalogStale);
 for(const [action,id] of [['newer','newerVersion'],['older','olderVersion'],['latest','latestVersion']])el(id).disabled=!targets[action];
}
function navigateVersion(action){
 if(mode==='images')return false;
 const id=versionNavigation(groups,mode!=='images'?designVersion:asset?.id,deleteBusy||confirmBusy||catalogStale)[action];
 if(!id)return false;
 if(mode!=='images')designVersion=id;chooseFromMenus(undefined,id);return true;
}
function renderStats(){
 el('stats').textContent=`${catalog.stats.directories||0} 个保存目录 · ${catalog.stats.models||0} 个模型文件 · ${catalog.stats.images||0} 张图片`;
}
function renderStorage(){
 const inventory=storageInventory(groups.flatMap(g=>g.assets).map(a=>catalog.assets.find(source=>source.id===a.id)||{...a,files:[]}));
 const media=mediaModes.find(m=>m.value===mode).label;
 el('categoryStorage').hidden=true;
 el('categoryStorage').textContent=`当前分类（${media}）· ${inventory.versions} ${mode==='images'?'张图片':'个版本'} · ${inventory.files} 个文件 · ${size(inventory.bytes)}（含源文件，路径去重；不含清理备份）`;
 if(!asset){el('assetStorage').textContent='';return;}
 if(mode==='images'){const picture=catalog.assets.flatMap(a=>a.files).find(f=>f.path===imagePath);el('assetStorage').textContent=picture?`当前图片：${size(picture.bytes)}${imageDimensions?' · '+imageDimensions:''}`:'当前内容暂无图片';return;}
 const currentPath=mode==='images'?imagePath:modelFile;
 const file=catalog.assets.flatMap(a=>a.files).find(f=>f.path===currentPath);
 const total=storageInventory([asset]);
 const detail=mode==='images'?imageDimensions:modelStats?`${modelStats.meshCount.toLocaleString()} 个网格部件 · ${modelStats.triangleCount.toLocaleString()} 个三角面`:'';
 if(asset.designObject&&designVersion==='live'){el('assetStorage').textContent=modelStats?`${modelStats.meshCount.toLocaleString()} 个部件 · ${modelStats.triangleCount.toLocaleString()} 个三角面`:'';return;}
 el('assetStorage').textContent=`当前${mode==='images'?'图片':'模型'}：${file?size(file.bytes):'暂无文件'}${detail?' · '+detail:''} ｜ 整个版本：${size(total.bytes)} · ${total.files} 个文件`;
}
function requestDeleteAsset(){
 if(!asset||deleteBusy||confirmBusy||catalogStale||asset.designVersion==='live')return;
 const scope=versionRemovalScope(designIndex,asset.id);
 if(scope.protected)return;
 if(!asset.designObject){deleteCurrentAsset();return;}
 pendingDelete=asset.id;
 el('deleteScope').textContent='删除整个保存版本「'+asset.title+'」'+(scope.labels.length?'，影响：'+scope.labels.join('、'):'')+'。保留共享文件与可恢复备份。';
 renderDeleteAction();
}
async function deleteCurrentAsset(){
 if(!asset||deleteBusy||confirmBusy||catalogStale||asset.designVersion==='live')return;
 const scope=versionRemovalScope(designIndex,asset.id);
 if(scope.protected)return;
 if(asset.designObject&&pendingDelete!==asset.id)return;
 pendingDelete=null;
 const target=asset,nextId=nextVersionAfterDeletion(groups,target.id);
 deleteBusy=true;deleteMessage='';renderDeleteAction();renderPickers();renderModes();
 let deleted=false;
 try{
  const response=await fetch('/assets/cleanup/assets/'+encodeURIComponent(target.id),{method:'DELETE'});
  if(!response.ok){const body=await response.json();throw new Error(body.detail||`请求失败（${response.status}）`);}
  const result=await response.json();deleted=true;
  const pending=await readCatalog(),updated=pending.catalog;await readReferences(updated);catalog=updated;designIndex=await readDesignIndex();catalogEtag=pending.etag;
  if(mode!=='images')designVersion=nextId;
  chooseFromMenus(undefined,nextId);renderStats();
  deleteMessage=`已删除「${target.title}」。已保留可恢复备份。`;
  el('deleteStatus').title='备份：build/asset_cleanup/'+result.backup;
 }catch(error){
  catalogStale=true;
  deleteMessage=(deleted?'已删除，但目录刷新失败：':'删除结果未确认：')+error.message+'。请刷新页面核对后再操作。';
  if(deleted){catalog.assets=catalog.assets.filter(a=>a.id!==target.id);asset=null;chooseFromMenus(undefined,nextId);}
 }finally{deleteBusy=false;renderPickers();renderModes();renderDeleteAction();}
}
function closeContentMenu(){
 el('contentMenu').hidden=true;el('contentTrigger').setAttribute('aria-expanded','false');
}
function positionContentMenu(){
 const popup=el('contentMenu');if(popup.hidden)return;
 const rect=el('contentTrigger').getBoundingClientRect(),width=popup.getBoundingClientRect().width;
 popup.style.top=(rect.bottom+6)+'px';
 popup.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-width-12))+'px';
}
function renderContentCascade(menu,selected){
 const trigger=el('contentTrigger'),popup=el('contentMenu');
 const tree=contentMenuTree(menu);
 const leaf=tree.flatMap(g=>g.children.flatMap(c=>c.children||[c])).find(c=>c.id===selected);
 trigger.textContent=(leaf?.label||menu.object?.label||'选择内容')+' ▾';
 trigger.disabled=confirmBusy||deleteBusy||catalogStale;
 popup.replaceChildren();closeContentMenu();
 function column(items,depth){
  while(popup.children.length>depth)popup.lastElementChild.remove();
  const panel=document.createElement('div');panel.className='cascade-column';panel.setAttribute('role','menu');popup.append(panel);
  for(const item of items.flatMap(item=>item.section?[{heading:item.label},...item.children]:item)){
   if(item.heading){const heading=document.createElement('div');heading.className='cascade-heading';heading.textContent=item.heading;panel.append(heading);continue;}
   const button=document.createElement('button');button.type='button';button.setAttribute('role','menuitem');button.textContent=item.label+(item.children?' ›':'');
   if(item.children){button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');}
   else if(item.id===selected)button.setAttribute('aria-current','true');
   button.onclick=()=>{
    for(const sibling of panel.children)if(sibling.hasAttribute('aria-haspopup'))sibling.setAttribute('aria-expanded','false');
    if(item.children){button.setAttribute('aria-expanded','true');column(item.children,depth+1);}
    else{closeContentMenu();chooseContent(item.id);trigger.focus();}
   };
   button.onkeydown=event=>{
    if(event.key==='ArrowRight'&&item.children){event.preventDefault();button.click();popup.lastElementChild.firstElementChild?.focus();}
    if(event.key==='ArrowLeft'&&depth>0){event.preventDefault();const previous=popup.children[depth-1];while(popup.children.length>depth)popup.lastElementChild.remove();positionContentMenu();previous.querySelector('[aria-expanded="true"]')?.focus();}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const choices=[...panel.querySelectorAll('button')],index=choices.indexOf(button);choices[(index+(event.key==='ArrowDown'?1:-1)+choices.length)%choices.length].focus();}
   };
   panel.append(button);
  }
  positionContentMenu();
 }
 trigger.onclick=()=>{
  if(!popup.hidden){closeContentMenu();return;}
  column(tree,0);popup.hidden=false;positionContentMenu();trigger.setAttribute('aria-expanded','true');popup.firstElementChild.querySelector('button')?.focus();
 };
}
document.addEventListener('click',event=>{if(!event.target.closest('.content-picker'))closeContentMenu();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!el('contentMenu').hidden){closeContentMenu();el('contentTrigger').focus();}});
window.addEventListener('resize',positionContentMenu);
window.addEventListener('scroll',positionContentMenu,true);
function renderDesignPickers(assetId){
 if(!designObject&&assetId){
  designObject=designIndex.objects.find(o=>o.group==='archive'&&o.versions.some(v=>v.id===assetId))?.id||'overview';
  designVersion=assetId;
 }
 const menu=designMenu(designIndex,designObject||'overview',designVersion);
 designObject=menu.object?.id||'overview';designVersion=menu.selected?.id||'';
 el('versionPicker').hidden=mode==='images';
 const content=el('categorySelect');content.replaceChildren();content.disabled=confirmBusy||deleteBusy||catalogStale;
 for(const group of menu.groups){const node=document.createElement('optgroup');node.label=group.label;
  for(const object of group.objects){const o=document.createElement('option');o.value=object.id;o.textContent=mode==='images'?`${object.label}（${objectImages(catalog,object.id).filter(e=>e.kind==='reference').length} 张参考图）`:object.compositionOnly?`${object.label}（组合查看）`:`${object.label}（${object.versionCount} 个版本${object.sourceCount?`，${object.sourceCount} 份源文件`:""}）`;node.append(o);}content.append(node);
 }
 content.value=menu.object?.collection||designObject;
 renderContentCascade(menu,content.value);
 const select=el('assetSelect');select.replaceChildren();select.disabled=confirmBusy||deleteBusy||catalogStale||!menu.selected;
 groups=[{assets:menu.versions.map(v=>({id:v.id}))}];
 for(const version of menu.versions){const o=document.createElement('option');o.value=version.id;
  const title=version.title?.replace(/\s*·\s*(?:待确认|已确认)$/,'')||version.id;
  o.textContent=version.id==='live'||version.members?title:version.historical?'历史 · '+(version.title||title):designObject==='overview'?'历史 · '+(version.title||title):title+' · '+adoptionLabel(designIndex.objects.find(o=>o.id===version.object)||menu.object,version);
  o.title=version.title||title;select.append(o);
 }
 if(menu.selected)select.value=menu.selected.id;
 const source=catalog.assets.find(a=>a.id===menu.selected?.asset);
 const synthetic=source?{...source,title:menu.selected.draft||menu.selected.members||menu.selected.sources?menu.selected.title:source.title,
  description:menu.selected.draft?"未编号工作稿：持续覆盖更新；确认后才保存正式版本。":menu.selected.members?"组合查看：分别引用独立对象；请在右侧选择具体楼层或露台后确认。":source.designObject?source.description:menu.selected.sources?`此对象独立版本；${menu.selected.sources.length} 份历史导出包含相同内容。预览来源：${source.title}。历史文件均保留。`:source.description,
  primaryModel:menu.selected.file,models:menu.selected.file?[menu.selected.file]:[]}:
  {id:'__confirmed_overview',title:'园区总览',description:'',models:[],files:[],images:[],modes:['central']};
 return menu.selected?{...synthetic,contentLabel:menu.object?.label,designObject,designVersion}:null;
}
function renderConfirmation(){
 const obj=designIndex.objects.find(o=>o.id===designObject);
 const button=el('confirmVersion');button.hidden=mode==='images'||rawPreview||!asset?.designObject||obj?.group==='overview'||!!obj?.historical;
 if(button.hidden)return;
 const adopted=!!loadedPlan?.adopted;
 const matches=adopted;
 button.textContent=confirmBusy?'确认中…':obj?.aggregate?(obj.collection==='layout:central'?'选择楼层后确认':'选择位置后确认'):matches?'已确认':'确认'+(obj?.label||'当前对象')+(designObject.startsWith('layout:central:')?'布置':'')+(['building:pod','layout:pod'].includes(designObject)?'（共用）':'');
 button.disabled=confirmBusy||deleteBusy||catalogStale||!loadedPlan?.confirmable||matches;
 button.title='仅确认'+(obj?.label||'当前对象')+'；参考显隐、查看楼层和相机不扩大确认范围';
}
async function confirmVersion(){
 if(!loadedPlan||confirmBusy||deleteBusy)return;
 pendingDelete=null;
 const target=loadedPlan;confirmBusy=true;deleteMessage='';renderDeleteAction();renderPickers();
 try{
  const r=await fetch('/assets/design/design/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sceneId:target.id,expectedCurrent:target.expectedCurrent})});
  if(!r.ok){const body=await r.json();throw new Error(body.detail||'确认失败');}
  const record=await r.json();designIndex=await readDesignIndex();
  if(designVersion==='draft'){designVersion=record.version;chooseFromMenus();return;}
  // Confirming changes only this object; references remain independently adopted.
  loadedPlan={...target,adopted:true,expectedCurrent:designIndex.objects.find(o=>o.id===designObject)?.current?.id};
 }catch(error){deleteMessage='确认失败：'+error.message;loadedPlan=null;}
 finally{confirmBusy=false;renderPickers();renderDeleteAction();}
}
function renderPickers(assetId=asset?.id){
 return renderDesignPickers(assetId);
}
function chooseContent(id){
 if(designObject&&designVersion)rememberedVersions.set(designObject,designVersion);
 designObject=id;designVersion=rememberedVersions.get(id)||'';
 imagePath='';manualReference='';chooseFromMenus();
}
function renderImageScope(){
 const terrace=designObject==='layout:terraces'||designObject.startsWith('layout:terrace:');
 el('imageScopeControl').hidden=!terrace;
 el('imageScopeHint').hidden=!terrace||!entries.some(e=>e.shared&&e.kind==='reference');
 const select=el('imageScope');select.replaceChildren();
 if(!terrace)return;
 const all=document.createElement('option');all.value='layout:terraces';all.textContent='八间合看';select.append(all);
 for(const object of designIndex.objects.filter(o=>o.id.startsWith('layout:terrace:')).sort((a,b)=>a.module.localeCompare(b.module))){
  const option=document.createElement('option');option.value=object.id;option.textContent=object.module;select.append(option);
 }
 select.value=designObject;
}
function renderDescription(description=''){
 const details=el('descriptionDetails'),text=el('assetDescription');
 text.textContent=description;text.title=description;
 details.open=false;details.hidden=!description;
}
function chooseFromMenus(params,assetId=asset?.id){
 const next=renderPickers(assetId);
 if(next)selectAsset(next,params);
 else{
  asset=null;entries=[];modelFile='';imagePath='';manualReference='';el('assetTitle').textContent='暂无可用版本';renderDescription();
  el('fileRows').replaceChildren();el('fileKinds').replaceChildren();el('sourcePath').textContent='';el('filesSummary').textContent='资产文件 · 0 个';
  showPreview();renderDeleteAction();
 }
}
function selectAsset(a,params){
 const objectChanged=asset?.designObject!==a.designObject;
 const changed=asset?.id!==a.id||objectChanged||asset?.designVersion!==a.designVersion;if(changed){pendingOrbit=null;pendingDelete=null;if(!catalogStale)deleteMessage='';}asset=a;entries=a.designObject?objectImages(catalog,a.designObject,a.designVersion):imageEntries(a,catalog);
 if(a.designObject&&a.designVersion)rememberedVersions.set(a.designObject,a.designVersion);
 if(objectChanged&&a.designObject&&!params?.has('object')){const obj=designIndex.objects.find(o=>o.id===a.designObject);view={...view,module:a.designObject==='overview'?'all':a.designObject==='layout:terraces'?'pods':obj?.module||'all',floor:obj?.floor||'all'};}
 const objectLabel=designIndex.objects.find(o=>o.id===a.designObject)?.label;
 el('assetTitle').textContent=objectLabel&&objectLabel!==a.title&&!a.title.startsWith(objectLabel+' · ')?objectLabel+' · '+a.title:a.title;
 if(mode==='images')el('assetTitle').textContent=(a.contentLabel||objectLabel||a.title)+(a.designObject?.startsWith('layout:terrace:')?' · '+designIndex.objects.find(o=>o.id===a.designObject)?.module:'')+' · 参考图片';
 renderDescription(mode==='images'?'设计参考按当前内容关联；模型检查图片另注明来源版本。':a.description||'');el('assetTitle').title=a.title;
 const requestedFile=params?.get('file')||(params?.get('view')?.startsWith('glb:')?params.get('view').slice(4):null);
 rawPreview=!!filePreviewSelection(designIndex,a,requestedFile,designObject);
 const models=rawPreview?[requestedFile]:a.designObject?a.models:workbenchMenus(catalog,mode,category,furniture,a.id).models;
 modelFile=models.includes(requestedFile)?requestedFile:!changed&&models.includes(modelFile)?modelFile:models[0]||'';
 const requestedMode=params?.get('view')?.startsWith('glb:')?'model':params?.get('view')||mode;
 if(mediaModes.some(m=>m.value===requestedMode))mode=requestedMode;
 if(changed||params){
  imageKind=Object.hasOwn(imageKinds,params?.get('imageKind'))?params.get('imageKind'):'all';
  imagePath=params?.get('image')||'';manualReference=params?.get('reference')||'';
 }
 if(mode!=='images'&&(changed||params)&&imageKind==='all'&&!params?.has('imageKind')&&entries.some(e=>e.kind==='reference'))imageKind='reference';
 const explicitImage=a.files.find(f=>f.kind==='image'&&f.path===imagePath);
 if(explicitImage&&!entries.some(e=>e.path===imagePath))entries.push({path:imagePath,name:explicitImage.name,kind:'file'});
 fileKind=a.models.length?'model':a.files.some(f=>f.kind==='source')?'source':'image';
 renderFiles();renderImageKinds();showPreview();renderDeleteAction();
}
function switchMode(next){if(designObject&&designVersion)rememberedVersions.set(designObject,designVersion);mode=next;if(next==='images')imageKind='all';if(next==='compare'&&designVersion==='live')designVersion=designIndex.objects.find(o=>o.id===designObject)?.versions[0]?.id||'';chooseFromMenus();}
function renderModes(){
 el('mediaModes').replaceChildren();
 for(const choice of mediaModes){
  const b=document.createElement('button');b.type='button';b.textContent=choice.label;b.setAttribute('aria-pressed',String(mode===choice.value));
  b.disabled=confirmBusy||deleteBusy||catalogStale||!asset||(choice.value==='compare'&&!entries.some(e=>e.kind==='reference'));b.onclick=()=>switchMode(choice.value);el('mediaModes').append(b);
 }
}
function showPreview(){
 renderStorage();
 renderModes();
 if(!asset||!asset.designObject&&!assetModes(asset,catalog).some(m=>m.value===mode)){
  frame.hidden=true;el('imageViewer').hidden=true;el('comparison').hidden=true;el('preview').classList.remove('comparing');el('empty').hidden=false;
  frame.removeAttribute('src');frame.dataset.source='';frame.dataset.ready='no';
  const label=mediaModes.find(m=>m.value===mode).label;el('empty').textContent=`当前分类暂无可用于${label}的版本。`;
  el('previewState').textContent='当前分类暂无版本';updateHash();return;
 }
 if(mode!=='images'&&!modelFile&&asset.designVersion!=='live'){
  frame.hidden=true;frame.removeAttribute('src');frame.dataset.source='';frame.dataset.ready='no';loadedPlan=null;
  el('imageViewer').hidden=true;el('comparison').hidden=true;el('preview').classList.remove('comparing');
  el('empty').hidden=false;el('empty').textContent='此版本仅保存源文件，可在下方资产文件中下载。';
  el('previewState').textContent='仅源文件';updateHash();return;
 }
 el('empty').hidden=true;frame.hidden=mode==='images';
 el('imageViewer').hidden=mode!=='images';el('comparison').hidden=mode!=='compare';el('preview').classList.toggle('comparing',mode==='compare');
 if(mode==='images'){frame.removeAttribute('src');frame.dataset.source='';frame.dataset.ready='no';renderImage();el('previewState').textContent='图片 · 参考／模型截图／布局尺寸';updateHash();return;}
 const query=new URLSearchParams({file:modelFile,asset:asset.id,embedded:'1'});
 if(exteriorPreview)query.set('exterior','1');
 if(asset.designObject&&!rawPreview){query.set('designObject',asset.designObject);query.set('revision',asset.designVersion);}
 const base='/assets/design/viewer.html?'+query;
 frame.title=asset.title+' · 三维模型';
 if(frame.dataset.source!==base){
  frame.dataset.source=base;frame.dataset.ready='no';capabilities={};modelStats=null;loadedPlan=null;renderConfirmation();renderStorage();
  const params=new URLSearchParams(query);writeView(params,view);frame.src='/assets/design/viewer.html?'+params;
 }else sendView(false);
 if(mode==='compare')renderComparison();
 el('previewState').textContent=frame.dataset.ready==='yes'?'三维预览 · 拖动旋转':'正在加载模型…';updateHash();
}
function sendView(fit,orbit){if(frame.dataset.ready==='yes'&&!frame.hidden)frame.contentWindow.postMessage({type:'asset-view',view,fit,orbit},location.origin);}
window.addEventListener('message',event=>{
 if(event.origin!==location.origin||event.source!==frame.contentWindow||!asset)return;
 const data=event.data;if(!data||data.asset!==asset.id||data.file!==modelFile)return;
 if(asset.designObject&&!rawPreview&&(data.designObject!==asset.designObject||data.revision!==asset.designVersion))return;
 if(data.type==='asset-layout'){
  if(Number.isFinite(data.minimumHeight)&&data.minimumHeight>0&&data.minimumHeight<10000)frame.style.minHeight=Math.ceil(data.minimumHeight)+'px';
  return;
 }
 if(data.type==='asset-scope'){
  const target=designIndex.objects.find(o=>o.id===data.object),current=designIndex.objects.find(o=>o.id===designObject);
  if(!target||target.collection!==current?.collection||target.historical)return;
  chooseContent(target.id);return;
 }
 if(data.type==='asset-view-mode'){
  if(!['overview','landscape:site'].includes(designObject))return;
  exteriorPreview=data.exterior===true;
  pendingOrbit=null;
  frame.dataset.source='';frame.dataset.ready='no';
  showPreview();updateHash();return;
 }
 if(data.type==='asset-ready'){
  loadedPlan=data.designPlan;renderConfirmation();
  capabilities=data.capabilities;view=normalizeView(view,capabilities);frame.dataset.ready='yes';sendView(true,pendingOrbit);pendingOrbit=null;
  const stats=frame.contentWindow.elfiePreview;
  modelStats=stats?.source===modelFile?{meshCount:stats.meshCount,triangleCount:stats.triangleCount}:null;renderStorage();
  if(!frame.hidden)el('previewState').textContent=rawPreview?'原始文件预览 · '+modelFile.split('/').pop():loadedPlan?.issues?.length?`${loadedPlan.issues.length} 项待确认／检查`:'三维预览 · 拖动旋转';
  el('previewState').title=loadedPlan?.issues?.map(i=>i.object+'：'+i.reason).join('\n')||'';
 }else if(data.type==='asset-change'&&!frame.hidden){
  const patch=Object.fromEntries(Object.keys(defaultView).filter(key=>Object.hasOwn(data.patch,key)).map(key=>[key,data.patch[key]]));
  view=normalizeView({...view,...patch},capabilities);sendView(['module','floor','camera'].some(key=>Object.hasOwn(patch,key)));
 }else if(data.type==='asset-error'){if(!frame.hidden)el('previewState').textContent='预览加载失败：'+data.message;return;}
 else return;
 if(mode==='compare')renderComparison();updateHash();
});
function renderImageKinds(){
 el('imageKind').replaceChildren();
 for(const [value,label] of Object.entries(imageKinds)){
  const count=value==='all'?entries.length:entries.filter(e=>e.kind===value).length;if(!count&&value!=='all')continue;
  const o=document.createElement('option');o.value=value;o.textContent=`${label} (${count})`;el('imageKind').append(o);
 }
 if(![...el('imageKind').options].some(o=>o.value===imageKind))imageKind='all';el('imageKind').value=imageKind;
}
function renderImage(){
 renderImageScope();
 const rows=gallery();let index=rows.findIndex(e=>e.path===imagePath);if(index<0)index=0;
 const selected=rows[index];imagePath=selected?.path||'';
 imageDimensions='';
 const groupLabel=selected?(imageKinds[selected.kind]||'资产文件图片'):'';
 el('heroImage').hidden=!selected;el('imageEmpty').hidden=!!selected;el('imageName').textContent=selected?`${index+1} / ${rows.length} · ${groupLabel} · ${selected.name}`:'';
 if(selected){el('heroImage').src=url(selected.path);el('heroImage').alt=`${asset.title} · ${groupLabel} · ${selected.name}`;}else el('heroImage').removeAttribute('src');
 el('previousImage').disabled=rows.length<2;el('nextImage').disabled=rows.length<2;el('imageStrip').replaceChildren();
 for(const e of rows){
  const b=document.createElement('button');b.setAttribute('aria-label',e.name);b.setAttribute('aria-pressed',String(e.path===imagePath));
  const img=document.createElement('img');img.src=url(e.path);img.loading='lazy';img.alt=e.name;
  const name=document.createElement('span');name.textContent=e.name;b.append(img,name);b.onclick=()=>{imagePath=e.path;renderImage();updateHash();};el('imageStrip').append(b);
 }
 renderStorage();
}
function referenceCandidates(){
 const refs=new Map(entries.filter(e=>e.kind==='reference').map(e=>[e.path,e]));

 return [...refs.values()];
}
function renderComparison(){
 const refs=referenceCandidates(),automatic=asset.designObject?refs[0]:modelFile===(asset.primaryModel||asset.models[0])?referenceFor(entries,view):undefined;
 const manual=refs.find(e=>e.path===manualReference);if(!manual)manualReference='';
 const selected=manual||automatic;el('referenceSelect').replaceChildren();
 const o=document.createElement('option');o.value='';o.textContent=automatic?'自动 · '+automatic.name:'自动 · 暂无对应参考';el('referenceSelect').append(o);
 for(const e of refs){const option=document.createElement('option');option.value=e.path;option.textContent='手动 · '+e.name;el('referenceSelect').append(option);}
 el('referenceSelect').value=manualReference;el('referenceImage').hidden=!selected;el('referenceEmpty').hidden=!!selected;
 if(selected){el('referenceImage').src=url(selected.path);el('referenceImage').alt=selected.name;}else el('referenceImage').removeAttribute('src');
 el('referenceStatus').textContent=manual?'手动参考：仅用于本次对照，未绑定当前对象。':automatic?asset.designObject?`当前内容参考：${automatic.name}`:automatic.module?`对应参考：${automatic.name}`:`设计参考：${automatic.name}（未绑定具体房间或楼层）`:'当前对象与楼层尚未关联参考图。';
 el('autoReference').hidden=!manual;
}
function previewFile(f){
 if(f.kind==='image'){
  mode='images';imageKind='all';imagePath=f.path;
  chooseFromMenus(new URLSearchParams({view:mode,image:f.path,imageKind:'all'}));
 }else if(f.kind==='model'){
  const selection=filePreviewSelection(designIndex,asset,f.path,designObject);if(!selection)return;
  mode='model';designObject=selection.object;designVersion=selection.version;
  chooseFromMenus(new URLSearchParams({view:mode,file:selection.file}));
 }
}
function renderFiles(){
 el('filesSummary').textContent=`资产文件 · ${asset.files.length} 个（模型、源文件、图片与数据）`;
 el('sourcePath').textContent='保存目录：devtools/asset_design/assets/'+(modelFile||asset.primaryModel||asset.files?.[0]?.path||'').split('/').slice(0,-1).join('/');
 el('fileKinds').replaceChildren();
 for(const [id,label] of Object.entries(kindLabels)){
  const count=id==='all'?asset.files.length:asset.files.filter(f=>f.kind===id).length;if(!count)continue;
  const b=document.createElement('button');b.textContent=label+' '+count;b.setAttribute('aria-pressed',String(fileKind===id));b.onclick=()=>{fileKind=id;renderFiles();};el('fileKinds').append(b);
 }
 el('fileRows').replaceChildren();
 for(const f of asset.files.filter(f=>fileKind==='all'||f.kind===fileKind)){
  const tr=document.createElement('tr'),name=document.createElement('td'),bytes=document.createElement('td'),actions=document.createElement('td');name.textContent=f.name;bytes.textContent=size(f.bytes);
  if(['model','image'].includes(f.kind)){const b=document.createElement('button');b.textContent=f.kind==='model'?'预览模型':'查看图片';b.onclick=()=>previewFile(f);actions.append(b);}
  const a=document.createElement('a');a.href=url(f.path)+'?download=1';a.download=f.name.split('/').pop();a.textContent='下载';actions.append(a);tr.append(name,bytes,actions);el('fileRows').append(tr);
 }
}
el('categorySelect').onchange=()=>chooseContent(el('categorySelect').value);
el('imageScope').onchange=()=>chooseContent(el('imageScope').value);
el('confirmVersion').onclick=confirmVersion;
el('deleteAsset').onclick=requestDeleteAsset;
el('deleteConfirm').onclick=deleteCurrentAsset;
el('deleteCancel').onclick=()=>{pendingDelete=null;renderDeleteAction();};
el('assetSelect').onchange=()=>{designVersion=el('assetSelect').value;chooseFromMenus(undefined,el('assetSelect').value);};
el('newerVersion').onclick=()=>navigateVersion('newer');
el('olderVersion').onclick=()=>navigateVersion('older');
el('latestVersion').onclick=()=>navigateVersion('latest');
window.addEventListener('keydown',event=>{
 const action=versionShortcut(event);
 if(action&&navigateVersion(action))event.preventDefault();
});
el('imageKind').onchange=()=>{imageKind=el('imageKind').value;imagePath='';renderImage();updateHash();};
el('heroImage').onload=()=>{imageDimensions=`${el('heroImage').naturalWidth} × ${el('heroImage').naturalHeight} 像素`;renderStorage();};
el('heroImage').onerror=()=>{imageDimensions='';renderStorage();};
function stepImage(delta){const rows=gallery();if(!rows.length)return;const index=rows.findIndex(e=>e.path===imagePath);imagePath=rows[(index+delta+rows.length)%rows.length].path;renderImage();updateHash();}
el('previousImage').onclick=()=>stepImage(-1);el('nextImage').onclick=()=>stepImage(1);
el('referenceSelect').onchange=()=>{manualReference=el('referenceSelect').value;renderComparison();updateHash();};el('autoReference').onclick=()=>{manualReference='';renderComparison();updateHash();};
window.addEventListener('popstate',()=>{
 const params=new URLSearchParams(location.hash.slice(1));view=readView(params);designObject=params.get('designObject')||'';designVersion=params.get('revision')||'';exteriorPreview=params.get('exterior')==='1';
 mode=mediaModes.some(m=>m.value===params.get('view'))?params.get('view'):'model';
 category=params.get('category')||'';furniture=params.get('furnitureCategory')||'';chooseFromMenus(params,params.get('asset'));
});
renderStats();
const seed=catalog.assets.find(a=>a.id===initial.get('asset'));
if(seed&&initial.get('asset'))category=workbenchMenus({assets:[seed]},assetModes(seed,catalog).some(m=>m.value===mode)?mode:'model').category||category;
chooseFromMenus(initial,seed?.id);
scheduleCatalogRefresh();
