import * as THREE from '/assets/design/library/three.module.js';
import {GLTFLoader} from '/assets/design/library/GLTFLoader.js';
import {loadDesignScene,batchStaticMeshes} from './scene-model.mjs';
import {createAdaptiveDetail,prepareAdaptiveDetail} from './adaptive-detail.mjs';
import {createCourtyardDetail} from './courtyard-detail.mjs';
import {createPreviewRenderer,previewLifecycle} from './preview-lifecycle.mjs';
import {applyAuthoredAppearance,createAuthoredEnvironment} from './authored-appearance.mjs';
import {installLightShaderLoops} from './light-shader-loops.mjs';
import {attachFixtureLights,updateFixtureLights} from './fixture-lights.mjs';
import {sceneVisibility} from './design-state.mjs';
import {clampInteriorOrbit,courtyardInterior,isInteriorPreview} from './interior-camera.mjs';
import {isInteriorSkySurface,isCourtyardBoundaryWall,overviewRenderLayers,overviewPreviewOptions} from './preview-policy.mjs';
import {OrbitControls} from '/assets/design/library/OrbitControls.js';
import {meshVisible,moduleSelected,deriveCapabilities,objectChoices,floorChoices,normalizeView,readView,frameable,measurementVisible,spansFloors,floorControlVisible} from '/assets/design/view-state.mjs';
const status=document.getElementById('status'),error=document.getElementById('error');
const params=new URLSearchParams(location.search),embedded=params.get('embedded')==='1'&&window.parent!==window;
if(embedded)document.body.classList.add('embedded');
function notify(type,data){if(embedded)window.parent.postMessage({type,asset:params.get('asset'),file:params.get('file')||'',designObject:params.get('designObject'),revision:params.get('revision'),...data},location.origin);}
if(embedded){
 const sidebar=document.querySelector('aside'),controls=document.getElementById('viewerControls'),footer=document.querySelector('.viewer-footer');
 let previousHeight=0;
 const layoutObserver=new ResizeObserver(()=>{
  const style=getComputedStyle(sidebar);
  const minimumHeight=Math.ceil(controls.getBoundingClientRect().height+parseFloat(style.paddingTop)+parseFloat(style.paddingBottom)+footer.getBoundingClientRect().height);
  if(minimumHeight!==previousHeight){previousHeight=minimumHeight;notify('asset-layout',{minimumHeight});}
 });
 layoutObserver.observe(controls);layoutObserver.observe(footer);
}

let preview={release:()=>{}};
try{
const previewStarted=performance.now();
const loadPhase=message=>{status.textContent=message;};
const file=params.get('file')||'';
const designObject=params.get('designObject');
const exteriorPreview=isInteriorPreview(designObject)&&params.get('exterior')==='1';
const composedExteriorPreview=designObject==='overview'&&exteriorPreview;
const courtyardPreview=isInteriorPreview(designObject);
document.getElementById('courtyardViewControls').hidden=!courtyardPreview;
let designPlan=null;
if(designObject){
 loadPhase('正在读取组合…');
 const query=new URLSearchParams({object:designObject});
 if(params.get('revision')&&params.get('revision')!=='live')query.set('version',params.get('revision'));
 const r=await fetch('/assets/design/design/scene?'+query,{cache:'no-store'});
 if(!r.ok)throw new Error('对象组合无法读取');designPlan=await r.json();
}
// Exterior inspection needs the estate shell and courtyard, not the interior
// furniture graph. Keep the full plan for metadata and controls, but do not
// download/clone dozens of layout and template sources just to hide them later.
const renderPlan=exteriorPreview&&designObject==='overview'&&designPlan?{
 ...designPlan,
 layers:overviewRenderLayers(designPlan.layers,{exterior:true}),
}:designPlan;
if(!designPlan&&(!file||!(/\.(glb|gltf)$/i).test(file)))throw new Error('请选择已保存的 GLB 或 GLTF 模型。');
const catalogResponse=await fetch('/assets/design/catalog.json');if(!catalogResponse.ok)throw new Error('资产目录无法读取');
loadPhase('正在准备资产索引…');
const catalog=await catalogResponse.json();
const asset=catalog.assets.find(a=>a.id===(designPlan?.layers[0]?.asset||params.get('asset')))||{modes:[],category:'estate',files:[]};
if(!designPlan&&!asset.files.some(f=>f.path===file&&f.kind==='model'))throw new Error('所选模型未登记在该资产中。');
const fileURL=p=>'/assets/design/files/'+p.split('/').map(encodeURIComponent).join('/');
let buffer=null;
if(!designPlan){loadPhase('正在下载模型…');const response=await fetch(fileURL(file));if(!response.ok)throw new Error('模型文件无法读取');buffer=await response.arrayBuffer();}
let measurements={dimensions:[],rulers:[],anchors:{}};
const measurementFile=designPlan?designPlan.layers[0]?.measurements:asset.measurements&&file===asset.primaryModel?asset.measurements:null;
if(measurementFile){const r=await fetch(fileURL(measurementFile));if(!r.ok)throw new Error('测量数据无法读取');measurements={...measurements,...await r.json()};}
const payload={measurements};
loadPhase(exteriorPreview?'正在解码庭院与建筑外壳…':'正在解码模型…');
const model=renderPlan?await loadDesignScene(renderPlan,fileURL):(await new Promise((resolve,reject)=>new GLTFLoader().parse(buffer,fileURL(file).replace(/[^/]*$/,''),resolve,reject))).scene;
const modelLoadedAt=performance.now();
loadPhase('正在准备材质与视角…');
const review=designPlan?.review;
if(review&&review.axis==='module'){
 document.getElementById('scopeControls').hidden=false;
 document.getElementById('scopeLabel').textContent={floor:'楼层',module:'露台位置',part:'套装部件'}[review.axis];
 fillSelect('reviewScope',review.choices.map(c=>({value:c.id,label:c.label})),review.object);
 document.getElementById('reviewScope').onchange=()=>notify('asset-scope',{object:document.getElementById('reviewScope').value});
}
const context=document.getElementById('contextControl');
if(designPlan){
 const hasReference=designPlan.layers.some(l=>l.reference);
 context.hidden=designObject==='overview'||!['building','layout','part'].includes(designPlan.layers[0]?.group)&&!designObject.startsWith('part:');
 document.getElementById('context').disabled=!hasReference;
 const pendingReference=designPlan.layers.some(l=>l.reference&&l.unconfirmed);
 document.getElementById('contextStatus').hidden=hasReference&&!pendingReference;
 document.getElementById('contextStatus').textContent=pendingReference?'最新 · 未确认':'暂无已确认版本';
 document.getElementById('contextLabel').textContent=designPlan.layers[0]?.group==='building'?'参考家具':designPlan.layers[0]?.group==='layout'?'参考建筑':'参考布置';
 context.title=hasReference?designPlan.layers.filter(l=>l.reference).map(l=>l.label+' · '+l.title).join('\n'):'暂无已确认参考';
 document.getElementById('furnitureControl').hidden=designObject!=='overview'||exteriorPreview;
}
model.updateMatrixWorld(true);
const modelBounds=new THREE.Box3().setFromObject(model),modelCenter=modelBounds.getCenter(new THREE.Vector3()),modelSize=modelBounds.getSize(new THREE.Vector3()),modelRadius=Math.max(.1,modelBounds.getBoundingSphere(new THREE.Sphere()).radius);
const estate=designPlan?designPlan.layers.some(l=>l.module==='central'||/^M\d{2}$/.test(l.module)):asset.modes.includes('central');
document.getElementById('modelName').textContent=designPlan?(designObject==='overview'?'当前确认组合':designPlan.layers[0]?.label||'暂无确认对象'):file.split('/').pop();
document.getElementById('modelSize').textContent=[modelSize.x,modelSize.z,modelSize.y].map(n=>n.toFixed(2)).join(' × ');

const canvas=document.getElementById('viewport'),stage=document.getElementById('stage');
const overviewProfile=designObject==='overview'?overviewPreviewOptions({exterior:exteriorPreview}):null;
const renderer=createPreviewRenderer(THREE,canvas,overviewProfile||{});
preview=previewLifecycle(renderer,window,{onRestore:()=>{dirty=true;}});
renderer.setPixelRatio(Math.min(devicePixelRatio,overviewProfile?.pixelRatioCap||1.75));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.88;
renderer.transmissionResolutionScale=overviewProfile?.transmissionResolutionScale||1;
renderer.localClippingEnabled=true;renderer.shadowMap.enabled=overviewProfile?.shadows??true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
// Saved preview geometry is static; camera movement does not change its shadow map.
renderer.shadowMap.autoUpdate=false;
const scene=new THREE.Scene();scene.background=new THREE.Color('#dce6e0');scene.add(model);
const ambient=new THREE.HemisphereLight(0xd7ebff,0x5a685d,.65);scene.add(ambient);
const exteriorLights=[];function sun(color,power,pos,shadow=false){const l=new THREE.DirectionalLight(color,power);l.position.set(...pos);l.castShadow=shadow;if(shadow){l.shadow.mapSize.set(2048,2048);Object.assign(l.shadow.camera,{left:-28,right:28,top:28,bottom:-28,near:1,far:100});l.shadow.bias=-.0002;l.shadow.normalBias=.015;}scene.add(l);exteriorLights.push(l);}
sun(0xffe7c3,2.8,[-20,35,24],!overviewProfile);sun(0xcdeaff,1.0,[22,25,-24]);sun(0xffffff,.35,[0,15,32]);
const ground=new THREE.Mesh(new THREE.CircleGeometry(20.5,128),new THREE.MeshStandardMaterial({color:0xc3d0c7,roughness:.95}));ground.rotation.x=-Math.PI/2;ground.position.y=-.13;ground.visible=!exteriorPreview;scene.add(ground);
ground.receiveShadow=true;
const camera=new THREE.PerspectiveCamera(42,1,.05,200);camera.position.set(4,27,47);
const controls=new OrbitControls(camera,canvas);controls.target.set(0,4.0,0);controls.enableDamping=(overviewProfile?.damping??true)&&!matchMedia('(prefers-reduced-motion: reduce)').matches;controls.dampingFactor=.09;controls.minDistance=2;controls.maxDistance=110;controls.maxPolarAngle=Math.PI*.51;controls.update();
// A soft studio environment gives the dome visible reflections without obscuring its interior.
const skyCanvas=document.createElement('canvas');skyCanvas.width=512;skyCanvas.height=256;const skyContext=skyCanvas.getContext('2d');const gradient=skyContext.createLinearGradient(0,0,0,256);gradient.addColorStop(0,'#b9e8fb');gradient.addColorStop(.48,'#78c9ed');gradient.addColorStop(1,'#4c9fd2');skyContext.fillStyle=gradient;skyContext.fillRect(0,0,512,256);skyContext.fillStyle='#f8fdff';for(const [x,y,w,h] of [[-40,28,240,70],[150,52,230,58],[350,24,240,72],[-70,112,260,62],[170,132,260,56],[390,116,210,66],[-100,198,300,50],[220,190,320,58]]){skyContext.beginPath();skyContext.ellipse(x+w*.5,y+h*.5,w*.5,h*.5,0,0,Math.PI*2);skyContext.fill();}const skyTexture=new THREE.CanvasTexture(skyCanvas);skyTexture.mapping=THREE.EquirectangularReflectionMapping;skyTexture.colorSpace=THREE.SRGBColorSpace;const skyBackground=new THREE.CanvasTexture(skyCanvas);skyBackground.mapping=THREE.UVMapping;skyBackground.colorSpace=THREE.SRGBColorSpace;skyBackground.needsUpdate=true;const pmrem=new THREE.PMREMGenerator(renderer);const skylightEnvironment=pmrem.fromEquirectangular(skyTexture).texture;pmrem.dispose();
const isSkyDome=isInteriorSkySurface;
const isExteriorRoof=object=>exteriorPreview&&/transparent large arch|arched roof/i.test(`${object.name} ${object.geometry?.name||''}`)&&!isSkyDome(object);
const domeSkyTexture=skyBackground.clone();domeSkyTexture.mapping=THREE.UVMapping;domeSkyTexture.needsUpdate=true;skyBackground.mapping=THREE.EquirectangularReflectionMapping;skyBackground.needsUpdate=true;
let authoredEnvironment=null;
model.traverse(o=>{if(o.isMesh&&(Array.isArray(o.material)?o.material:[o.material]).some(m=>m.userData?.preview_surface_finish))authoredEnvironment??=createAuthoredEnvironment(THREE,renderer);});
if(authoredEnvironment)window.addEventListener('pagehide',()=>authoredEnvironment.dispose(),{once:true});
const originalBoundaryMaterials=new Map();
if(exteriorPreview)model.traverse(o=>{
 if(!o.isMesh||!isCourtyardBoundaryWall(o))return;
 const materials=Array.isArray(o.material)?o.material:[o.material];
 for(const m of materials)originalBoundaryMaterials.set(m,{
  map:m.map,color:m.color?.clone?.(),transparent:m.transparent,opacity:m.opacity,
  depthWrite:m.depthWrite,roughness:m.roughness,metalness:m.metalness,
  emissive:m.emissive?.clone?.(),emissiveIntensity:m.emissiveIntensity,transmission:m.transmission,
 });
});
const meshes=[];let triangleCount=0;
model.traverse(o=>{if(!o.isMesh||o.userData.designExcluded)return;if(!o.userData.module){let p=o.parent;while(p&&!p.userData.module)p=p.parent;if(p)o.userData={...p.userData,...o.userData};}meshes.push(o);triangleCount+=(o.geometry.index?o.geometry.index.count:o.geometry.attributes.position.count)/3;
o.castShadow=!o.userData.glass;o.receiveShadow=!o.userData.glass;
if(o.userData.full_height)o.material=Array.isArray(o.material)?o.material.map(m=>m.clone()):o.material.clone();const materials=Array.isArray(o.material)?o.material:[o.material];
for(const m of materials){m.side=THREE.DoubleSide;if(applyAuthoredAppearance(m,authoredEnvironment?.texture)&&!isSkyDome(o))continue;if(isSkyDome(o)){if(!m.map)m.map=domeSkyTexture;else{m.map.colorSpace=THREE.SRGBColorSpace;m.map.needsUpdate=true;}const domeOpacity=.94;m.needsUpdate=true;m.transparent=domeOpacity<1;m.opacity=domeOpacity;m.depthWrite=domeOpacity>=1;m.transmission=0;m.roughness=.9;m.metalness=0;m.color.set(0xffffff);if(m.emissive)m.emissive.set(0x000000);m.emissiveIntensity=0;}else if(exteriorPreview&&isCourtyardBoundaryWall(o)){m.map=null;m.color.set(0xc8d4ca);m.transparent=false;m.opacity=1;m.depthWrite=true;m.roughness=.82;m.metalness=0;if(m.emissive)m.emissive.set(0x000000);m.needsUpdate=true;}else if(isExteriorRoof(o)){m.transparent=true;m.opacity=.38;m.depthWrite=false;m.transmission=0;m.roughness=.24;m.metalness=0;m.color.set(0xeaf1eb);m.needsUpdate=true;}else if(o.userData.glass){if(o.userData.roof_skylight){m.transmission=.82;m.transparent=false;m.opacity=1;m.depthWrite=true;m.roughness=.055;m.ior=1.46;m.thickness=.04;m.clearcoat=.8;m.clearcoatRoughness=.035;m.envMap=skylightEnvironment;m.envMapIntensity=1.3;m.color.set(0xa5e6ef);}else{m.transmission=0;m.transparent=true;m.opacity=.075;m.depthWrite=false;m.roughness=.18;m.color.set(0xcce6df);}}else{m.roughness=Math.max(.28,m.roughness||.4);m.metalness=Math.min(.18,m.metalness||0);}}
});
// The exterior inspection uses the authored final wall materials. The generic
// exterior pass may have neutralized them, so restore the exact source maps
// and colors instead of substituting a generated preview sky.
for(const [m,state] of originalBoundaryMaterials){
 m.map=state.map;if(m.map)m.map.needsUpdate=true;
 if(state.color)m.color.copy(state.color);
 m.transparent=state.transparent;m.opacity=state.opacity;m.depthWrite=state.depthWrite;
 m.roughness=state.roughness;m.metalness=state.metalness;
 if(state.emissive&&m.emissive)m.emissive.copy(state.emissive);
 m.emissiveIntensity=state.emissiveIntensity;m.transmission=state.transmission;m.needsUpdate=true;
}
let dirty=true;
const architectural=!!designPlan||file===asset.primaryModel&&['estate','central','pod','early'].includes(asset.category);
const capabilities=deriveCapabilities(architectural?meshes.map(o=>o.userData):[]);
let view=normalizeView(readView(params),capabilities);
if(overviewProfile&&!overviewProfile.showFurnitureByDefault)view={...view,furniture:false,context:false};
const meshBounds=new Map(meshes.map(o=>{if(!o.geometry.boundingBox)o.geometry.computeBoundingBox();return[o,o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld)];}));
const interiorPreview=isInteriorPreview(designObject)&&!exteriorPreview,boundaryBounds=new THREE.Box3();
if(interiorPreview){
 for(const mesh of meshes){
  if(mesh.userData.designObject!=='landscape:site'||mesh.userData.preview_backdrop
   ||!/boundary.*rim|courtyard.*boundary|site.*boundary/i.test(mesh.name))continue;
  boundaryBounds.union(meshBounds.get(mesh));
 }
}
const interiorCamera=!boundaryBounds.isEmpty()?courtyardInterior({
 min:{x:boundaryBounds.min.x,z:boundaryBounds.min.z},max:{x:boundaryBounds.max.x,z:boundaryBounds.max.z},
}):null;
if(interiorCamera){
 controls.enablePan=false;
 controls.maxDistance=interiorCamera.radius;
 controls.target.fromArray(interiorCamera.center);
 controls.update();
}
const ranges={};
for(const [module,floors] of Object.entries(capabilities)){
 const boxes=floors.map(floor=>{const box=new THREE.Box3();for(const o of meshes){const p=o.userData;if(p.module===module&&!p.full_height&&!p.reference&&String(p.floor||1)===floor)box.union(meshBounds.get(o));}return box;});
 floors.forEach((floor,i)=>{const box=boxes[i],next=boxes[i+1];if(!box.isEmpty())ranges[module+':'+floor]=[box.min.y-.005,next&&!next.isEmpty()&&next.min.y>box.min.y?next.min.y-.005:box.max.y+.005];});
}
// Older shells carry one floor tag even where their geometry crosses storeys.
for(const mesh of meshes){
 const box=meshBounds.get(mesh),p=mesh.userData;
 const starts=(capabilities[p.module]||[]).map(floor=>ranges[p.module+':'+floor]?.[0]).filter(Number.isFinite);
 if(!p.full_height&&spansFloors(p,box.min.y,box.max.y,starts)){
  p.full_height=true;
  mesh.material=Array.isArray(mesh.material)?mesh.material.map(m=>m.clone()):mesh.material.clone();
 }
}

const interiorLights=[];
const fixtureLights=meshes.flatMap(mesh=>attachFixtureLights(mesh,THREE));
const batchCandidates=exteriorPreview?meshes.filter(mesh=>!mesh.userData.furniture&&!mesh.userData.reference):meshes;
const staticBatches=designObject==='overview'?batchStaticMeshes(batchCandidates,scene):null;
if(overviewProfile?.motionLod)staticBatches?.setMotion(true);
controls.addEventListener('start',()=>{staticBatches?.setMotion(true);dirty=true;});
controls.addEventListener('end',()=>{if(!overviewProfile?.motionLod)staticBatches?.setMotion(false);dirty=true;});
installLightShaderLoops([...meshes.flatMap(mesh=>Array.isArray(mesh.material)?mesh.material:[mesh.material]),ground.material],THREE);
const litFloors=new Set(fixtureLights.filter(e=>e.mesh.userData.module==='central').map(e=>Number(e.mesh.userData.floor)));
for(let i=0;i<8;i++){const a=(-40+i*260/7)*Math.PI/180;const l=new THREE.PointLight(0xffc889,0,8,2);l.position.set(13.55*Math.cos(a),1.75,-13.55*Math.sin(a));scene.add(l);interiorLights.push(l);}
for(const h of [2.5,5.8,8.5]){const l=new THREE.PointLight(0xffd49d,0,11,2);l.position.set(0,h,0);scene.add(l);interiorLights.push(l);}
const nookLights=(payload.measurements.furniture_lamps_world_m||[]).map(p=>{const l=new THREE.PointLight(0xffcd8f,1.1,2.2,2);l.position.set(p[0],p[2],-p[1]);scene.add(l);return l;});
const exteriorBackground=new THREE.Color('#d5d9d7');
const neutralBackground=new THREE.Color('#dce6e0');
function setLighting(dusk){scene.background=composedExteriorPreview?(dusk?new THREE.Color('#152b43'):exteriorBackground):neutralBackground;ambient.intensity=dusk?.48:.72;ambient.groundColor.set(dusk&&fixtureLights.length?0xb0a99a:0x5a685d);ground.material.color.set(dusk?0x253c3c:0xc3d0c7);exteriorLights.forEach((l,i)=>{l.intensity=dusk?[1.0,.65,.22][i]:[1.05,.65,.30][i];l.color.set(dusk?[0x99c2ff,0xa5b2ff,0xc2d9ff][i]:[0xffe7c3,0xcdeaff,0xffffff][i]);});interiorLights.forEach((l,i)=>l.intensity=i>=8&&litFloors.has(i-7)?0:dusk?(i<8?48:95):(i<8?3:12));updateFixtureLights(fixtureLights,dusk);document.getElementById('day').setAttribute('aria-pressed',String(!dusk));document.getElementById('dusk').setAttribute('aria-pressed',String(dusk));dirty=true;}

function fillSelect(id,choices,value){
 const select=document.getElementById(id);select.replaceChildren();
 for(const choice of choices){const option=document.createElement('option');option.value=choice.value;option.textContent=choice.label;select.append(option);}
 select.value=value;
}
function applyView(next,fit=false){
 renderer.shadowMap.needsUpdate=true;
 view=normalizeView(next,capabilities);
 const objects=objectChoices(capabilities),floors=floorChoices(capabilities,view.module);
 fillSelect('module',objects,view.module);fillSelect('floor',floors,view.floor);
 document.getElementById('objectControls').hidden=objects.length<=2||review?.axis==='module'||!!designPlan&&designObject!=='overview'&&!['building:pod','layout:pod'].includes(designObject);
 document.getElementById('floorControls').hidden=!floorControlVisible(floors,review);
 for(const key of ['glass','scale','furniture','dimensions','ruler','context'])document.getElementById(key).checked=view[key]&&(key!=='context'||!document.getElementById(key).disabled);
 for(const o of meshes){const p=o.userData;o.visible=(!designPlan||sceneVisibility(p,view,designObject))&&meshVisible(p,designPlan&&designObject!=='overview'?{...view,furniture:true}:view)
   &&(view.floor==='all'||!p.full_height||!!ranges[p.module+':'+view.floor]);
  if(p.full_height){const range=view.floor==='all'?null:ranges[p.module+':'+view.floor];const materials=Array.isArray(o.material)?o.material:[o.material];
   for(const material of materials)material.clippingPlanes=range?[new THREE.Plane(new THREE.Vector3(0,1,0),-range[0]),new THREE.Plane(new THREE.Vector3(0,-1,0),range[1])]:[];
  }
 }
 document.getElementById('whole').setAttribute('aria-pressed',String(!view.section));document.getElementById('section').setAttribute('aria-pressed',String(view.section));
 document.getElementById('interiorView').setAttribute('aria-pressed',String(courtyardPreview&&!exteriorPreview));document.getElementById('exteriorView').setAttribute('aria-pressed',String(courtyardPreview&&exteriorPreview));
 for(const light of nookLights)light.visible=view.furniture&&moduleSelected(view.module,'M01')&&(view.floor==='all'||view.floor==='1');
 for(const [id,preset] of [['reset','fit'],['front','front'],['top','top'],['rear','rear'],['side','side']])document.getElementById(id).setAttribute('aria-pressed',String(view.camera===preset));
 setLighting(view.light==='dusk');updateMeasurementLayers();const bounds=visibleBounds();const size=bounds.getSize(new THREE.Vector3());document.getElementById('modelSize').textContent=[size.x,size.z,size.y].map(n=>n.toFixed(2)).join(' × ');if(fit)fitView(bounds);staticBatches?.sync(true,{camera});
 const objectName=designPlan&&designObject!=='overview'?designPlan.layers[0]?.label||'对象':objects.find(o=>o.value===view.module).label,floorName=floors.find(f=>f.value===view.floor).label,previewScope=exteriorPreview?'庭院外部检查':'庭院内部';
 status.textContent=designPlan&&!meshes.length?'尚无已确认版本':`${previewScope} · ${objectName} · ${floorName} · ${view.section?'剖视':'整体'} · 拖动旋转`;dirty=true;
}
function changeView(patch){
 if(embedded)notify('asset-change',{patch});
 else applyView({...view,...patch},['module','floor','camera'].some(key=>Object.hasOwn(patch,key)));
}
function changeCourtyardView(exterior){
 if(!courtyardPreview||exterior===exteriorPreview)return;
 if(embedded){notify('asset-view-mode',{exterior});return;}
 const next=new URL(location.href);
 if(exterior)next.searchParams.set('exterior','1');else next.searchParams.delete('exterior');
 location.href=next.href;
}
function visibleBounds(){
 const bounds=new THREE.Box3();
 for(const mesh of meshes){if(!mesh.visible||isSkyDome(mesh)||!frameable(mesh.userData,mesh.name,capabilities))continue;const box=meshBounds.get(mesh).clone();
  const range=view.floor==='all'?null:ranges[mesh.userData.module+':'+view.floor];
  if(mesh.userData.full_height&&range){box.min.y=Math.max(box.min.y,range[0]);box.max.y=Math.min(box.max.y,range[1]);}
  if(!box.isEmpty())bounds.union(box);
 }
 return bounds;
}
function keepInsideCourtyard(){
 if(!interiorCamera)return false;
 const orbit=clampInteriorOrbit(camera.position.toArray(),controls.target.toArray(),interiorCamera);
 const changed=orbit.position.some((value,index)=>value!==camera.position.getComponent(index))
  ||orbit.target.some((value,index)=>value!==controls.target.getComponent(index));
 if(!changed)return false;
 camera.position.fromArray(orbit.position);controls.target.fromArray(orbit.target);return true;
}
function fitView(bounds){
 if(bounds.isEmpty())return;
 const center=interiorCamera?new THREE.Vector3().fromArray(interiorCamera.center):bounds.getCenter(new THREE.Vector3()),radius=Math.max(.1,bounds.getBoundingSphere(new THREE.Sphere()).radius);
 const anchor=measurements.anchors[view.module];
 const front=anchor?point(anchor.front).sub(point(anchor.center)).normalize():new THREE.Vector3(0,0,1);
 const right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),front).normalize();
const interiorLift=interiorCamera?0:exteriorPreview?.55:.7,frontLift=interiorCamera?0:exteriorPreview?.3:.35;
 const direction=view.camera==='top'?new THREE.Vector3(.001,1,.002):view.camera==='rear'?front.clone().negate().add(new THREE.Vector3(0,frontLift,0))
  :view.camera==='side'?right.add(new THREE.Vector3(0,frontLift,0)):view.camera==='front'?front.clone().add(new THREE.Vector3(0,frontLift,0))
  :front.clone().addScaledVector(right,.3).add(new THREE.Vector3(0,interiorLift,0));
 const angle=Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*Math.min(1,camera.aspect));
 const distance=interiorCamera?Math.min(radius/Math.sin(angle)*1.08,interiorCamera.radius*.78):radius/Math.sin(angle)*1.08;
 controls.target.copy(center);controls.maxDistance=interiorCamera?interiorCamera.radius:Math.max(110,distance*4);controls.minDistance=interiorCamera?Math.min(Math.max(2,radius*.08),interiorCamera.radius*.6):radius*.08;
 camera.far=Math.max(500,distance+radius*10);camera.updateProjectionMatrix();camera.position.copy(center).addScaledVector(direction.normalize(),distance);controls.update();keepInsideCourtyard();dirty=true;
}
const dimensionLayer=new THREE.Group(),rulerLayer=new THREE.Group();scene.add(dimensionLayer,rulerLayer);
const dimensionGroups=[],rulerGroups=[];
const point=p=>new THREE.Vector3(p[0],p[2],-p[1]);
function label(text,position,height=.26,color='#184f72'){
 const c=document.createElement('canvas');const ctx=c.getContext('2d');ctx.font='600 44px sans-serif';c.width=Math.ceil(ctx.measureText(text).width+38);c.height=76;ctx.font='600 44px sans-serif';ctx.fillStyle='#ffffffed';ctx.fillRect(0,0,c.width,c.height);ctx.fillStyle=color;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,c.width/2,38);
 const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false,depthWrite:false}));sprite.position.copy(position);sprite.scale.set(height*c.width/c.height,height,1);sprite.renderOrder=20;return sprite;
}
function line(group,a,b,color=0x236994){const g=new THREE.BufferGeometry().setFromPoints([a,b]);const o=new THREE.Line(g,new THREE.LineBasicMaterial({color,depthTest:false,depthWrite:false}));o.renderOrder=15;group.add(o);}
for(const entry of measurements.dimensions){
 const group=new THREE.Group(),a=point(entry.a),b=point(entry.b),span=b.clone().sub(a),mid=a.clone().add(b).multiplyScalar(.5);const tick=entry.vertical?new THREE.Vector3(.16,0,0):new THREE.Vector3(-span.z,0,span.x).normalize().multiplyScalar(.16);
 line(group,a,b);for(const end of [a,b])line(group,end.clone().sub(tick),end.clone().add(tick));mid.add(tick.clone().multiplyScalar(1.8));group.add(label(entry.label,mid,entry.module==='central'||entry.module==='all'?.47:.27));group.userData=entry;dimensionLayer.add(group);dimensionGroups.push(group);
}
for(const entry of measurements.rulers){
 const group=new THREE.Group(),a=point(entry.a),b=point(entry.b),direction=b.clone().sub(a).normalize();const tick=entry.vertical?new THREE.Vector3(.12,0,0):new THREE.Vector3(-direction.z,0,direction.x).multiplyScalar(.12);line(group,a,b,0x9b592d);
 for(let distance=0;distance<=entry.length;distance+=.5){const p=a.clone().addScaledVector(direction,distance),major=Number.isInteger(distance);line(group,p,p.clone().addScaledVector(tick,major?2:1),0x9b592d);if(major)group.add(label(`${distance}${distance===entry.length?' m':''}`,p.clone().addScaledVector(tick,4),entry.length>4?.36:.23,'#814623'));}
 group.userData=entry;rulerLayer.add(group);rulerGroups.push(group);
}
function updateMeasurementLayers(){
 const top=Math.abs(camera.position.clone().sub(controls.target).normalize().y)>.94;
 dimensionLayer.visible=view.dimensions;rulerLayer.visible=view.ruler;
 for(const group of [...dimensionGroups,...rulerGroups])group.visible=measurementVisible(group.userData,view,ranges[group.userData.module+':'+view.floor])&&(!group.userData.vertical||!top)&&(!group.userData.label?.startsWith('床')||view.furniture);
}
for(const id of ['module','floor'])document.getElementById(id).onchange=()=>changeView({[id]:document.getElementById(id).value});
for(const id of ['glass','scale','furniture','dimensions','ruler','context'])document.getElementById(id).onchange=()=>changeView({[id]:document.getElementById(id).checked});
document.getElementById('whole').onclick=()=>changeView({section:false});document.getElementById('section').onclick=()=>changeView({section:true});
document.getElementById('day').onclick=()=>changeView({light:'day'});document.getElementById('dusk').onclick=()=>changeView({light:'dusk'});
for(const [id,cameraPreset] of [['reset','fit'],['front','front'],['top','top'],['rear','rear'],['side','side']])document.getElementById(id).onclick=()=>changeView({camera:cameraPreset});
document.getElementById('interiorView').onclick=()=>changeCourtyardView(false);document.getElementById('exteriorView').onclick=()=>changeCourtyardView(true);
window.addEventListener('message',event=>{
 if(embedded&&event.origin===location.origin&&event.source===window.parent&&event.data?.type==='asset-view'){
  applyView(event.data.view,event.data.fit);
  const orbit=event.data.orbit;
  if(orbit&&[orbit.position,orbit.target].every(v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite))){
   camera.position.fromArray(orbit.position);controls.target.fromArray(orbit.target);controls.update();keepInsideCourtyard();controls.update();dirty=true;
  }
 }
});
for(const [id,factor] of [['zoomIn',.8],['zoomOut',1.25]])document.getElementById(id).onclick=()=>{const offset=camera.position.clone().sub(controls.target);offset.setLength(Math.min(controls.maxDistance,Math.max(controls.minDistance,offset.length()*factor)));camera.position.copy(controls.target).add(offset);controls.update();dirty=true;};
document.getElementById('download').disabled=!!designPlan;
if(designPlan)document.getElementById('download').title='原始 GLB 可从资产文件下载';document.getElementById('download').onclick=()=>{const url=URL.createObjectURL(new Blob([buffer],{type:'model/gltf-binary'}));const a=document.createElement('a');a.href=url;a.download=file.split('/').pop();a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();dirty=true;}
new ResizeObserver(resize).observe(stage);resize();
if(!estate&&!modelBounds.isEmpty()){ground.geometry.dispose();ground.geometry=new THREE.CircleGeometry(modelRadius*2.5,128);ground.position.set(modelCenter.x,modelBounds.min.y-.01,modelCenter.z);camera.near=Math.max(.001,modelRadius/500);camera.updateProjectionMatrix();}
const detailCenter=interiorCamera?.center||[modelCenter.x,modelCenter.y,modelCenter.z];
const courtyardDetail=designObject==='overview'?createCourtyardDetail(meshes,{exterior:exteriorPreview}):null;
courtyardDetail?.update(camera,{center:detailCenter,force:true});
applyView(view,true);
const adaptiveDetail=overviewProfile?.adaptiveGeometry?createAdaptiveDetail(meshes):null;
const detailAbort=new AbortController();
window.addEventListener('pagehide',()=>{detailAbort.abort();adaptiveDetail?.dispose();courtyardDetail?.dispose();},{once:true});
if(!await preview.prepare(scene,camera,{precompile:!overviewProfile}))throw new DOMException('Preview closed','AbortError');
loadPhase('正在完成首帧…');
console.debug('asset-preview-timing '+JSON.stringify({modelMs:Math.round(modelLoadedAt-previewStarted),firstFrameMs:Math.round(performance.now()-previewStarted),drawCalls:renderer.info.render.calls,submittedTriangles:renderer.info.render.triangles,staticBatches:staticBatches?.batches.length||0,gpuTextures:renderer.info.memory.textures,textureSharing:model.userData.previewTextureSharing,courtyardDetail:courtyardDetail?.stats()}));
notify('asset-ready',{capabilities,designPlan:designPlan?{id:designPlan.id,expectedCurrent:designPlan.expectedCurrent,confirmable:designPlan.confirmable,adopted:designPlan.adopted,refs:designPlan.layers.filter(l=>l.reference).map(l=>({object:l.object,version:l.version,digest:l.digest,contentDigest:l.contentDigest})),issues:designPlan.issues}:null});
if(designPlan&&!meshes.length)status.textContent='尚无已确认版本';
let detailReported=false;
 let cullFrame=0;
 function animate(){const moved=controls.update(),kept=keepInsideCourtyard(),detailChanged=courtyardDetail?.update(camera,{center:detailCenter})||false;if((moved||kept)&&cullFrame++%4===0)staticBatches?.sync(true,{camera});if(moved||kept||detailChanged||dirty){
 const shadowUpdate=renderer.shadowMap.needsUpdate;
 adaptiveDetail?.update(camera,stage.clientHeight*renderer.getPixelRatio(),{fullDetail:shadowUpdate,fullTextures:false});
 if(adaptiveDetail)renderer.transmissionResolutionScale=adaptiveDetail.transmissionScale();
 updateMeasurementLayers();const start=performance.now();renderer.render(scene,camera);
 const renderSubmitMs=performance.now()-start;dirty=!!shadowUpdate;
 if(adaptiveDetail&&detailReported){detailReported=false;console.debug('asset-preview-detail '+JSON.stringify({...adaptiveDetail.stats(),submittedTriangles:renderer.info.render.triangles,drawCalls:renderer.info.render.calls,renderSubmitMs}));}
}}
renderer.setAnimationLoop(animate);
if(adaptiveDetail)prepareAdaptiveDetail(adaptiveDetail,{workerURL:new URL('/assets/design/library/meshopt_simplifier.module.js',location.href).href,signal:detailAbort.signal,onChange:()=>{dirty=true;}}).then(()=>{if(!detailAbort.signal.aborted){detailReported=true;dirty=true;}}).catch(error=>{if(error.name!=='AbortError')console.error('Preview detail preparation failed',error);});
window.elfiePreview={ready:true,designPlan,context:()=>meshes.filter(m=>m.visible&&m.userData.designReference).length,meshCount:meshes.length,triangleCount,source:file,state:()=>({section:view.section,floor:document.getElementById('floor').value,camera:camera.position.toArray(),visible:meshes.filter(m=>m.visible).length,references:meshes.filter(m=>m.visible&&m.userData.reference).length,furniture:meshes.filter(m=>m.visible&&m.userData.furniture).length,dimensionLabels:dimensionGroups.filter(g=>g.visible&&dimensionLayer.visible).map(g=>g.userData.label),rulerGroups:rulerGroups.filter(g=>g.visible&&rulerLayer.visible).length,courtyard:interiorCamera?{center:interiorCamera.center,radius:interiorCamera.radius,panLocked:!controls.enablePan}:null})};
window.elfiePreview.orbit=()=>({position:camera.position.toArray(),target:controls.target.toArray()});
}catch(e){preview.release();if(e.name!=='AbortError'){status.textContent='载入失败';error.style.display='block';error.textContent='预览没有成功载入：'+e.message+'。请使用支持 WebGL 的新版 Chrome、Edge 或 Safari 打开此文件。';notify('asset-error',{message:e.message});console.error(e);}}
