import * as THREE from '/assets/design/library/three.module.js';
import {GLTFLoader} from '/assets/design/library/GLTFLoader.js';
import {OrbitControls} from '/assets/design/library/OrbitControls.js';
import {meshVisible,moduleSelected,deriveCapabilities,objectChoices,floorChoices,normalizeView,readView,frameable,measurementVisible} from '/assets/design/view-state.mjs';
const status=document.getElementById('status'),error=document.getElementById('error');
const params=new URLSearchParams(location.search),embedded=params.get('embedded')==='1'&&window.parent!==window;
if(embedded)document.body.classList.add('embedded');
function notify(type,data){if(embedded)window.parent.postMessage({type,asset:params.get('asset'),file:params.get('file'),...data},location.origin);}

try{
const file=params.get('file');
if(!file||!(/\.(glb|gltf)$/i).test(file))throw new Error('请选择已保存的 GLB 或 GLTF 模型。');
const catalogResponse=await fetch('/assets/design/catalog.json');if(!catalogResponse.ok)throw new Error('资产目录无法读取');
const catalog=await catalogResponse.json();
const asset=catalog.assets.find(a=>a.id===params.get('asset'));
if(!asset||!asset.files.some(f=>f.path===file&&f.kind==='model'))throw new Error('所选模型未登记在该资产中。');
const fileURL=p=>'/assets/design/files/'+p.split('/').map(encodeURIComponent).join('/');
const response=await fetch(fileURL(file));if(!response.ok)throw new Error('模型文件无法读取');
const buffer=await response.arrayBuffer();
let measurements={dimensions:[],rulers:[],anchors:{}};
if(asset.measurements&&file===asset.primaryModel){const r=await fetch(fileURL(asset.measurements));if(!r.ok)throw new Error('测量数据无法读取');measurements=await r.json();}
const payload={measurements};
const gltf=await new Promise((resolve,reject)=>new GLTFLoader().parse(buffer,fileURL(file).slice(0,fileURL(file).lastIndexOf('/')+1),resolve,reject));
const model=gltf.scene;
model.updateMatrixWorld(true);
const modelBounds=new THREE.Box3().setFromObject(model),modelCenter=modelBounds.getCenter(new THREE.Vector3()),modelSize=modelBounds.getSize(new THREE.Vector3()),modelRadius=Math.max(.1,modelBounds.getBoundingSphere(new THREE.Sphere()).radius);
const estate=asset.modes.includes('central');
document.getElementById('modelName').textContent=file.split('/').pop();
document.getElementById('modelSize').textContent=[modelSize.x,modelSize.z,modelSize.y].map(n=>n.toFixed(2)).join(' × ');

const canvas=document.getElementById('viewport'),stage=document.getElementById('stage');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.75));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.88;
renderer.localClippingEnabled=true;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
const scene=new THREE.Scene();scene.background=new THREE.Color('#dce6e0');scene.add(model);
const ambient=new THREE.HemisphereLight(0xd7ebff,0x5a685d,.65);scene.add(ambient);
const exteriorLights=[];function sun(color,power,pos,shadow=false){const l=new THREE.DirectionalLight(color,power);l.position.set(...pos);l.castShadow=shadow;if(shadow){l.shadow.mapSize.set(2048,2048);Object.assign(l.shadow.camera,{left:-28,right:28,top:28,bottom:-28,near:1,far:100});l.shadow.bias=-.0002;l.shadow.normalBias=.015;}scene.add(l);exteriorLights.push(l);}
sun(0xffe7c3,2.8,[-20,35,24],true);sun(0xcdeaff,1.0,[22,25,-24]);sun(0xffffff,.35,[0,15,32]);
const ground=new THREE.Mesh(new THREE.CircleGeometry(20.5,128),new THREE.MeshStandardMaterial({color:0xc3d0c7,roughness:.95}));ground.rotation.x=-Math.PI/2;ground.position.y=-.13;scene.add(ground);
ground.receiveShadow=true;
const camera=new THREE.PerspectiveCamera(42,1,.05,200);camera.position.set(4,27,47);
const controls=new OrbitControls(camera,canvas);controls.target.set(0,4.0,0);controls.enableDamping=!matchMedia('(prefers-reduced-motion: reduce)').matches;controls.dampingFactor=.09;controls.minDistance=2;controls.maxDistance=110;controls.maxPolarAngle=Math.PI*.51;controls.update();
// A soft studio environment gives the dome visible reflections without obscuring its interior.
const skyCanvas=document.createElement('canvas');skyCanvas.width=512;skyCanvas.height=256;const skyContext=skyCanvas.getContext('2d');const gradient=skyContext.createLinearGradient(0,0,0,256);gradient.addColorStop(0,'#c3e5f3');gradient.addColorStop(.48,'#365867');gradient.addColorStop(1,'#112e36');skyContext.fillStyle=gradient;skyContext.fillRect(0,0,512,256);skyContext.fillStyle='#edfaff';skyContext.fillRect(70,28,105,24);skyContext.fillStyle='#99dbe9';skyContext.fillRect(320,48,70,45);const skyTexture=new THREE.CanvasTexture(skyCanvas);skyTexture.mapping=THREE.EquirectangularReflectionMapping;skyTexture.colorSpace=THREE.SRGBColorSpace;const pmrem=new THREE.PMREMGenerator(renderer);const skylightEnvironment=pmrem.fromEquirectangular(skyTexture).texture;skyTexture.dispose();pmrem.dispose();
const meshes=[];let triangleCount=0;
model.traverse(o=>{if(!o.isMesh)return;if(!o.userData.module){let p=o.parent;while(p&&!p.userData.module)p=p.parent;if(p)o.userData={...p.userData,...o.userData};}meshes.push(o);triangleCount+=(o.geometry.index?o.geometry.index.count:o.geometry.attributes.position.count)/3;
o.castShadow=!o.userData.glass;o.receiveShadow=!o.userData.glass;
if(o.userData.full_height)o.material=Array.isArray(o.material)?o.material.map(m=>m.clone()):o.material.clone();const materials=Array.isArray(o.material)?o.material:[o.material];
for(const m of materials){m.side=THREE.DoubleSide;if(o.userData.glass){if(o.userData.roof_skylight){m.transmission=.82;m.transparent=false;m.opacity=1;m.depthWrite=true;m.roughness=.055;m.ior=1.46;m.thickness=.04;m.clearcoat=.8;m.clearcoatRoughness=.035;m.envMap=skylightEnvironment;m.envMapIntensity=1.3;m.color.set(0xa5e6ef);}else{m.transmission=0;m.transparent=true;m.opacity=.075;m.depthWrite=false;m.roughness=.18;m.color.set(0xcce6df);}}else{m.roughness=Math.max(.28,m.roughness||.4);m.metalness=Math.min(.18,m.metalness||0);}}
});
let dirty=true;
const architectural=file===asset.primaryModel&&['estate','central','pod','early'].includes(asset.category);
const capabilities=deriveCapabilities(architectural?meshes.map(o=>o.userData):[]);
let view=normalizeView(readView(params),capabilities);
const meshBounds=new Map(meshes.map(o=>{o.geometry.computeBoundingBox();return[o,o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld)];}));
const ranges={};
for(const [module,floors] of Object.entries(capabilities)){
 const boxes=floors.map(floor=>{const box=new THREE.Box3();for(const o of meshes){const p=o.userData;if(p.module===module&&!p.full_height&&!p.reference&&String(p.floor||1)===floor)box.union(meshBounds.get(o));}return box;});
 floors.forEach((floor,i)=>{const box=boxes[i],next=boxes[i+1];if(!box.isEmpty())ranges[module+':'+floor]=[box.min.y-.005,next&&!next.isEmpty()&&next.min.y>box.min.y?next.min.y-.005:box.max.y+.005];});
}

const interiorLights=[];
for(let i=0;i<8;i++){const a=(-40+i*260/7)*Math.PI/180;const l=new THREE.PointLight(0xffc889,0,8,2);l.position.set(13.55*Math.cos(a),1.75,-13.55*Math.sin(a));scene.add(l);interiorLights.push(l);}
for(const h of [2.5,5.8,8.5]){const l=new THREE.PointLight(0xffd49d,0,11,2);l.position.set(0,h,0);scene.add(l);interiorLights.push(l);}
const nookLights=(payload.measurements.furniture_lamps_world_m||[]).map(p=>{const l=new THREE.PointLight(0xffcd8f,1.1,2.2,2);l.position.set(p[0],p[2],-p[1]);scene.add(l);return l;});
function setLighting(dusk){scene.background.set(dusk?'#152b43':'#dce6e0');ambient.intensity=dusk?.48:.72;ground.material.color.set(dusk?0x253c3c:0xc3d0c7);exteriorLights.forEach((l,i)=>{l.intensity=dusk?[1.0,.65,.22][i]:[1.05,.65,.30][i];l.color.set(dusk?[0x99c2ff,0xa5b2ff,0xc2d9ff][i]:[0xffe7c3,0xcdeaff,0xffffff][i]);});interiorLights.forEach((l,i)=>l.intensity=dusk?(i<8?48:95):(i<8?3:12));document.getElementById('day').setAttribute('aria-pressed',String(!dusk));document.getElementById('dusk').setAttribute('aria-pressed',String(dusk));dirty=true;}

function fillSelect(id,choices,value){
 const select=document.getElementById(id);select.replaceChildren();
 for(const choice of choices){const option=document.createElement('option');option.value=choice.value;option.textContent=choice.label;select.append(option);}
 select.value=value;
}
function applyView(next,fit=false){
 view=normalizeView(next,capabilities);
 const objects=objectChoices(capabilities),floors=floorChoices(capabilities,view.module);
 fillSelect('module',objects,view.module);fillSelect('floor',floors,view.floor);
 document.getElementById('objectControls').hidden=objects.length===1;
 document.getElementById('floorControls').hidden=floors.length===1;
 for(const key of ['glass','scale','furniture','dimensions','ruler'])document.getElementById(key).checked=view[key];
 for(const o of meshes){const p=o.userData;o.visible=meshVisible(p,view);
  if(p.full_height){const range=view.floor==='all'?null:ranges[p.module+':'+view.floor];const materials=Array.isArray(o.material)?o.material:[o.material];
   for(const material of materials)material.clippingPlanes=range?[new THREE.Plane(new THREE.Vector3(0,1,0),-range[0]),new THREE.Plane(new THREE.Vector3(0,-1,0),range[1])]:[];
  }
 }
 document.getElementById('whole').setAttribute('aria-pressed',String(!view.section));document.getElementById('section').setAttribute('aria-pressed',String(view.section));
 for(const light of nookLights)light.visible=view.furniture&&moduleSelected(view.module,'M01')&&(view.floor==='all'||view.floor==='1');
 for(const [id,preset] of [['reset','fit'],['front','front'],['top','top'],['rear','rear'],['side','side']])document.getElementById(id).setAttribute('aria-pressed',String(view.camera===preset));
 setLighting(view.light==='dusk');updateMeasurementLayers();const bounds=visibleBounds();const size=bounds.getSize(new THREE.Vector3());document.getElementById('modelSize').textContent=[size.x,size.z,size.y].map(n=>n.toFixed(2)).join(' × ');if(fit)fitView(bounds);
 const objectName=objects.find(o=>o.value===view.module).label,floorName=floors.find(f=>f.value===view.floor).label;
 status.textContent=`${objectName} · ${floorName} · ${view.section?'剖视':'整体'} · 拖动旋转`;dirty=true;
}
function changeView(patch){
 if(embedded)notify('asset-change',{patch});
 else applyView({...view,...patch},['module','floor','camera'].some(key=>Object.hasOwn(patch,key)));
}
function visibleBounds(){
 const bounds=new THREE.Box3();
 for(const mesh of meshes){if(!mesh.visible||!frameable(mesh.userData,mesh.name,capabilities))continue;const box=meshBounds.get(mesh).clone();
  const range=view.floor==='all'?null:ranges[mesh.userData.module+':'+view.floor];
  if(mesh.userData.full_height&&range){box.min.y=Math.max(box.min.y,range[0]);box.max.y=Math.min(box.max.y,range[1]);}
  if(!box.isEmpty())bounds.union(box);
 }
 return bounds;
}
function fitView(bounds){
 if(bounds.isEmpty())return;
 const center=bounds.getCenter(new THREE.Vector3()),radius=Math.max(.1,bounds.getBoundingSphere(new THREE.Sphere()).radius);
 const anchor=measurements.anchors[view.module];
 const front=anchor?point(anchor.front).sub(point(anchor.center)).normalize():new THREE.Vector3(0,0,1);
 const right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),front).normalize();
 const direction=view.camera==='top'?new THREE.Vector3(.001,1,.002):view.camera==='rear'?front.clone().negate().add(new THREE.Vector3(0,.35,0))
  :view.camera==='side'?right.add(new THREE.Vector3(0,.35,0)):view.camera==='front'?front.clone().add(new THREE.Vector3(0,.35,0))
  :front.clone().addScaledVector(right,.3).add(new THREE.Vector3(0,.7,0));
 const angle=Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*Math.min(1,camera.aspect));
 const distance=radius/Math.sin(angle)*1.08;
 controls.target.copy(center);controls.maxDistance=Math.max(110,distance*4);controls.minDistance=radius*.08;
 camera.far=Math.max(200,distance+radius*10);camera.updateProjectionMatrix();camera.position.copy(center).addScaledVector(direction.normalize(),distance);controls.update();dirty=true;
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
for(const id of ['glass','scale','furniture','dimensions','ruler'])document.getElementById(id).onchange=()=>changeView({[id]:document.getElementById(id).checked});
document.getElementById('whole').onclick=()=>changeView({section:false});document.getElementById('section').onclick=()=>changeView({section:true});
document.getElementById('day').onclick=()=>changeView({light:'day'});document.getElementById('dusk').onclick=()=>changeView({light:'dusk'});
for(const [id,cameraPreset] of [['reset','fit'],['front','front'],['top','top'],['rear','rear'],['side','side']])document.getElementById(id).onclick=()=>changeView({camera:cameraPreset});
window.addEventListener('message',event=>{
 if(embedded&&event.origin===location.origin&&event.source===window.parent&&event.data?.type==='asset-view')applyView(event.data.view,event.data.fit);
});
for(const [id,factor] of [['zoomIn',.8],['zoomOut',1.25]])document.getElementById(id).onclick=()=>{const offset=camera.position.clone().sub(controls.target);offset.setLength(Math.min(controls.maxDistance,Math.max(controls.minDistance,offset.length()*factor)));camera.position.copy(controls.target).add(offset);controls.update();dirty=true;};
document.getElementById('download').disabled=false;document.getElementById('download').onclick=()=>{const url=URL.createObjectURL(new Blob([buffer],{type:'model/gltf-binary'}));const a=document.createElement('a');a.href=url;a.download=file.split('/').pop();a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();dirty=true;}
new ResizeObserver(resize).observe(stage);resize();
if(!estate){ground.geometry.dispose();ground.geometry=new THREE.CircleGeometry(modelRadius*2.5,128);ground.position.set(modelCenter.x,modelBounds.min.y-.01,modelCenter.z);camera.near=Math.max(.001,modelRadius/500);camera.updateProjectionMatrix();}
applyView(view,true);notify('asset-ready',{capabilities});
function animate(){requestAnimationFrame(animate);const moved=controls.update();if(moved||dirty){updateMeasurementLayers();renderer.render(scene,camera);dirty=false;}}
animate();
window.elfiePreview={ready:true,meshCount:meshes.length,triangleCount,source:file,state:()=>({section:view.section,floor:document.getElementById('floor').value,camera:camera.position.toArray(),visible:meshes.filter(m=>m.visible).length,references:meshes.filter(m=>m.visible&&m.userData.reference).length,furniture:meshes.filter(m=>m.visible&&m.userData.furniture).length,dimensionLabels:dimensionGroups.filter(g=>g.visible&&dimensionLayer.visible).map(g=>g.userData.label),rulerGroups:rulerGroups.filter(g=>g.visible&&rulerLayer.visible).length})};
}catch(e){status.textContent='载入失败';error.style.display='block';error.textContent='预览没有成功载入：'+e.message+'。请使用支持 WebGL 的新版 Chrome、Edge 或 Safari 打开此文件。';notify('asset-error',{message:e.message});console.error(e);}
