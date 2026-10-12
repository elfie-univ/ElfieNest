import {readView,writeView,normalizeView,previewChoices,defaultView} from '/assets/design/view-state.mjs';
const catalog=await fetch('/assets/design/catalog.json').then(r=>{if(!r.ok)throw new Error('资产目录无法读取');return r.json();});
const categories=[['estate','整体园区'],['central','中央楼'],['pod','小房子'],['furniture','家具'],['concept','效果图'],['early','早期房间'],['review','审阅页'],['all','全部资产']];
const labels=Object.fromEntries(categories),kindLabels={model:'模型',source:'Blender 源文件',image:'图片',viewer:'预览页面',data:'尺寸 / 数据',support:'构建与辅助文件',all:'全部文件'};
const el=id=>document.getElementById(id),url=p=>'/assets/design/files/'+p.split('/').map(encodeURIComponent).join('/');
const size=n=>n>=1024**3?(n/1024**3).toFixed(2)+' GB':n>=1024**2?(n/1024**2).toFixed(1)+' MB':n>=1024?(n/1024).toFixed(1)+' KB':n+' B';
let category='estate',asset=null,mode='model',fileKind='model',imageIndex=0;
const frame=el('viewer');
const initial=new URLSearchParams(location.hash.slice(1));
let view=readView(initial),capabilities={};
const defaults={estate:'elfie_ground_lounge_fixed_stair_v1',central:'elfie_ground_lounge_fixed_stair_v1',pod:'elfie_central_reference_refine_v1',furniture:'elfie_furniture_kit_v17',concept:'design_references',early:'elfie_room_blender_v2',review:'elfie_curve_review_v12',all:'elfie_ground_lounge_fixed_stair_v1'};
function belongs(a,c){return c==='all'||a.category===c||(c==='central'&&a.category==='estate'&&a.modes.includes('central'))||(c==='pod'&&a.category==='estate'&&a.modes.includes('M01'));}
function matching(){const q=el('search').value.trim().toLowerCase();return catalog.assets.filter(a=>belongs(a,category)&&(!q||(a.title+' '+a.description+' '+a.id+' '+a.files.map(f=>f.name).join(' ')).toLowerCase().includes(q))).sort((a,b)=>((b.version??-1)-(a.version??-1))||a.title.localeCompare(b.title,'zh-CN'));}
function optionTitle(a){const origin=a.id.startsWith('checkpoint_')?'2026-10-03 保留快照':a.version?'园区第 '+a.version+' 版':a.title;if(category==='central'&&a.category==='estate')return a.version?origin+'中的中央楼':a.title;if(category==='pod'&&a.category==='estate')return origin+'中的房间';return a.title;}
function nav(){el('categories').replaceChildren();for(const [id,label] of categories){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(category===id));b.onclick=()=>{category=id;el('search').value='';renderChoices();};el('categories').append(b);}}
function renderChoices(preferred){
 nav();const rows=matching();el('assetSelect').replaceChildren();const groups=new Map();
 for(const a of rows){const groupName=labels[a.category];let group=groups.get(groupName);if(!group){group=document.createElement('optgroup');group.label=groupName;groups.set(groupName,group);el('assetSelect').append(group);}const o=document.createElement('option');o.value=a.id;o.textContent=optionTitle(a);group.append(o);}
 renderVersionGrid(rows);
 const next=rows.find(a=>a.id===preferred)||rows.find(a=>a.id===asset?.id)||rows.find(a=>a.id===defaults[category])||rows[0];
 if(next){el('empty').hidden=true;if(next.id===asset?.id){el('assetSelect').value=next.id;el('assetTitle').textContent=optionTitle(next);updateHash();}else selectAsset(next,asset?null:initial.get('view'));}
 else{asset=null;frame.src='about:blank';frame.dataset.source='';frame.hidden=true;el('imageViewer').hidden=true;el('empty').hidden=false;el('assetTitle').textContent='没有匹配结果';el('assetDescription').textContent='清空查找内容即可查看本类别全部资产。';el('modeSelect').replaceChildren();el('fileRows').replaceChildren();el('previewState').textContent='';}
}
function selectAsset(a,requestedMode){
 asset=a;el('assetSelect').value=a.id;el('assetTitle').textContent=optionTitle(a);el('assetDescription').textContent=a.description;
 el('modeSelect').replaceChildren();const choices=previewChoices(a);
 for(const {value,label} of choices){const o=document.createElement('option');o.value=value;o.textContent=label;el('modeSelect').append(o);}
 const preferred=requestedMode||mode;mode=choices.some(c=>c.value===preferred)?preferred:choices[0]?.value;
 el('modeSelect').value=mode;imageIndex=0;fileKind=a.models.length?'model':a.files.some(f=>f.kind==='source')?'source':'image';renderFiles();showPreview();
}
function updateHash(){if(!asset)return;const params=new URLSearchParams({category,asset:asset.id,view:mode});writeView(params,view);history.replaceState(null,'','#'+params);}
function showPreview(){
 if(!asset||!mode)return;updateHash();el('modeSelect').value=mode;
 if(mode==='images'){frame.hidden=true;frame.src='about:blank';frame.dataset.source='';frame.dataset.ready='no';el('imageViewer').hidden=false;renderImage();el('previewState').textContent='保存效果图';return;}
 el('imageViewer').hidden=true;frame.hidden=false;
 const file=mode.startsWith('glb:')?mode.slice(4):asset.primaryModel;
 const base='/assets/design/viewer.html?'+new URLSearchParams({file,asset:asset.id,embedded:'1'});
 frame.title=optionTitle(asset)+' · '+el('modeSelect').selectedOptions[0].textContent;
 if(frame.dataset.source===base){sendView(false);return;}
 frame.dataset.source=base;frame.dataset.ready='no';capabilities={};el('previewState').textContent='正在加载所选预览…';
 const params=new URLSearchParams({file,asset:asset.id,embedded:'1'});writeView(params,view);frame.src='/assets/design/viewer.html?'+params;
}
function sendView(fit){
 if(frame.dataset.ready!=='yes'||frame.hidden)return;
 frame.contentWindow.postMessage({type:'asset-view',view,fit},location.origin);
}
window.addEventListener('message',event=>{
 if(event.origin!==location.origin||event.source!==frame.contentWindow||!asset||frame.hidden)return;
 const data=event.data;if(!data||data.asset!==asset.id||data.file!==(mode.startsWith('glb:')?mode.slice(4):asset.primaryModel))return;
 if(data.type==='asset-ready'){
  capabilities=data.capabilities;view=normalizeView(view,capabilities);frame.dataset.ready='yes';updateHash();sendView(true);el('previewState').textContent='三维预览 · 拖动旋转';
 }else if(data.type==='asset-change'){
  const patch=Object.fromEntries(Object.keys(defaultView).filter(key=>Object.hasOwn(data.patch,key)).map(key=>[key,data.patch[key]]));
  view=normalizeView({...view,...patch},capabilities);updateHash();sendView(['module','floor','camera'].some(key=>Object.hasOwn(patch,key)));
 }else if(data.type==='asset-error')el('previewState').textContent='预览加载失败：'+data.message;
});
window.addEventListener('popstate',()=>{
 const params=new URLSearchParams(location.hash.slice(1));view=readView(params);category=labels[params.get('category')]?params.get('category'):category;
 renderChoices(params.get('asset'));if(asset)selectAsset(asset,params.get('view'));
});
function renderImage(){const images=asset.images;if(!images.length)return;imageIndex=(imageIndex+images.length)%images.length;const p=images[imageIndex],name=p.split('/').pop();el('heroImage').src=url(p);el('heroImage').alt=asset.title+' · '+name;el('imageName').textContent=`${imageIndex+1} / ${images.length} · ${name==='exec-34eda38c-ad37-4903-91ae-f02bc8db72df.png'?'已选床桌设计参考图':name}`;el('imageStrip').replaceChildren();for(const [i,path]of images.entries()){const b=document.createElement('button');b.setAttribute('aria-label','查看第 '+(i+1)+' 张效果图');b.setAttribute('aria-pressed',String(i===imageIndex));const img=document.createElement('img');img.src=url(path);img.loading='lazy';img.alt=path.split('/').pop();b.append(img);b.onclick=()=>{imageIndex=i;renderImage();};el('imageStrip').append(b);}}
function renderVersionGrid(rows){el('versionsSummary').textContent=`${labels[category]} · ${rows.length} 个可查看项（展开缩略图）`;el('versionGrid').replaceChildren();for(const a of rows){const b=document.createElement('button');b.className='version-card';b.setAttribute('aria-label','查看 '+optionTitle(a));if(a.thumbnail){const img=document.createElement('img');img.src=url(a.thumbnail);img.loading='lazy';img.alt=optionTitle(a)+' 的保存截图';b.append(img);}else{const marker=document.createElement('div');marker.className='no-image';marker.textContent=a.primaryModel?'3D':'源文件';b.append(marker);}const strong=document.createElement('strong');strong.textContent=optionTitle(a);const description=document.createElement('span');description.textContent=a.primaryModel?'原始 3D 预览':a.models.length?'独立模型':'效果图与源文件';b.append(strong,description);b.onclick=()=>{el('assetSelect').value=a.id;selectAsset(a);el('assetTitle').scrollIntoView({block:'start'});};el('versionGrid').append(b);}}
function previewFile(f){if(f.kind==='image'){mode='images';imageIndex=asset.images.indexOf(f.path);if(imageIndex<0){asset={...asset,images:[...asset.images,f.path]};imageIndex=asset.images.length-1;}showPreview();}else if(f.kind==='model'){mode='glb:'+f.path;if(![...el('modeSelect').options].some(o=>o.value===mode)){const o=document.createElement('option');o.value=mode;o.textContent='独立模型 · '+f.name;el('modeSelect').append(o);}showPreview();}}
function renderFiles(){if(!asset)return;el('filesSummary').textContent=`资产文件 · ${asset.files.length} 个（模型、源文件、图片与数据）`;el('sourcePath').textContent='保存目录：build/asset_previews/'+(asset.id==='design_references'?'asset_library/references':asset.id);el('fileKinds').replaceChildren();for(const [id,label]of Object.entries(kindLabels)){const count=id==='all'?asset.files.length:asset.files.filter(f=>f.kind===id).length;if(!count)continue;const b=document.createElement('button');b.textContent=label+' '+count;b.setAttribute('aria-pressed',String(fileKind===id));b.onclick=()=>{fileKind=id;renderFiles();};el('fileKinds').append(b);}el('fileRows').replaceChildren();for(const f of asset.files.filter(f=>fileKind==='all'||f.kind===fileKind)){const tr=document.createElement('tr'),name=document.createElement('td'),bytes=document.createElement('td'),actions=document.createElement('td');name.textContent=f.name;bytes.textContent=size(f.bytes);if(['model','image'].includes(f.kind)){const b=document.createElement('button');b.textContent=f.kind==='model'?'预览模型':'看图';b.onclick=()=>previewFile(f);actions.append(b);}const a=document.createElement('a');a.href=url(f.path)+'?download=1';a.download=f.name.split('/').pop();a.textContent='下载';actions.append(a);tr.append(name,bytes,actions);el('fileRows').append(tr);}}
el('assetSelect').onchange=()=>selectAsset(catalog.assets.find(a=>a.id===el('assetSelect').value));el('modeSelect').onchange=()=>{mode=el('modeSelect').value;showPreview();};el('search').oninput=()=>renderChoices();el('previousImage').onclick=()=>{imageIndex--;renderImage();};el('nextImage').onclick=()=>{imageIndex++;renderImage();};
el('stats').textContent=`${catalog.stats.directories||0} 个保存目录 · ${catalog.stats.models||0} 个模型文件 · ${catalog.stats.sources||0} 个 Blender 文件 · ${catalog.stats.images||0} 张图片`;
if(labels[initial.get('category')])category=initial.get('category');renderChoices(initial.get('asset')||defaults[category]);
