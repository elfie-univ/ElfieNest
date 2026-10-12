import * as THREE from '/assets/design/library/three.module.js';
import {GLTFLoader} from '/assets/design/library/GLTFLoader.js';
import {OrbitControls} from '/assets/design/library/OrbitControls.js';
import {meshVisible} from '/assets/design/view-state.mjs';
const status=document.getElementById('status'),error=document.getElementById('error');
try{
const params=new URLSearchParams(location.search),file=params.get('file');
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
let dirty=true,section=false;
const interiorLights=[];
for(let i=0;i<8;i++){const a=(-40+i*260/7)*Math.PI/180;const l=new THREE.PointLight(0xffc889,0,8,2);l.position.set(13.55*Math.cos(a),1.75,-13.55*Math.sin(a));scene.add(l);interiorLights.push(l);}
for(const h of [2.5,5.8,8.5]){const l=new THREE.PointLight(0xffd49d,0,11,2);l.position.set(0,h,0);scene.add(l);interiorLights.push(l);}
const nookLights=(payload.measurements.furniture_lamps_world_m||[]).map(p=>{const l=new THREE.PointLight(0xffcd8f,1.1,2.2,2);l.position.set(p[0],p[2],-p[1]);scene.add(l);return l;});
function setLighting(dusk){scene.background.set(dusk?'#152b43':'#dce6e0');ambient.intensity=dusk?.48:.72;ground.material.color.set(dusk?0x253c3c:0xc3d0c7);exteriorLights.forEach((l,i)=>{l.intensity=dusk?[1.0,.65,.22][i]:[1.05,.65,.30][i];l.color.set(dusk?[0x99c2ff,0xa5b2ff,0xc2d9ff][i]:[0xffe7c3,0xcdeaff,0xffffff][i]);});interiorLights.forEach((l,i)=>l.intensity=dusk?(i<8?48:95):(i<8?3:12));document.getElementById('day').setAttribute('aria-pressed',String(!dusk));document.getElementById('dusk').setAttribute('aria-pressed',String(dusk));dirty=true;}
document.getElementById('day').onclick=()=>setLighting(false);document.getElementById('dusk').onclick=()=>setLighting(true);setLighting(true);
function applyView(){const floor=document.getElementById('floor').value;const showGlass=document.getElementById('glass').checked;const showScale=document.getElementById('scale').checked;const module=document.getElementById('module').value;
for(const o of meshes){const p=o.userData;o.visible=meshVisible(p,{module,floor,section,glass:showGlass,scale:showScale,furniture:document.getElementById('furniture').checked});if(p.full_height){const ranges={'1':[.06,4.3],'2':[4.3,7.1],'3':[7.1,9.9],'4':[9.9,13.4]};const range=ranges[floor];const mats=Array.isArray(o.material)?o.material:[o.material];for(const m of mats)m.clippingPlanes=range?[new THREE.Plane(new THREE.Vector3(0,1,0),-range[0]),new THREE.Plane(new THREE.Vector3(0,-1,0),range[1])]:[];}}
document.getElementById('whole').setAttribute('aria-pressed',String(!section));document.getElementById('section').setAttribute('aria-pressed',String(section));
for(const l of nookLights)l.visible=document.getElementById('furniture').checked&&(module==='all'||module==='M01')&&(floor==='all'||floor==='1');
status.textContent=`${module==='all'?'全巢':module==='central'?'中央楼':module} · ${section?'剖视':'整体'} · ${floor==='all'?'全部楼层':floor==='4'?'屋顶':floor+' 楼'} · 拖动旋转`;dirty=true;}
document.getElementById('whole').onclick=()=>{section=false;applyView();};document.getElementById('section').onclick=()=>{section=true;applyView();};
for(const id of ['floor','glass','scale','module'])document.getElementById(id).onchange=applyView;
function focusModule(){
 const selected=document.getElementById('module').value;
 if(selected==='all'){controls.target.copy(modelCenter);camera.position.copy(modelCenter).add(new THREE.Vector3(.2,.9,1.6).multiplyScalar(modelRadius));}
 else{model.updateMatrixWorld(true);const bounds=new THREE.Box3();for(const o of meshes)if(o.visible)bounds.expandByObject(o);if(!bounds.isEmpty()){const center=bounds.getCenter(new THREE.Vector3());const size=bounds.getSize(new THREE.Vector3()).length();const direction=camera.position.clone().sub(controls.target).normalize();controls.target.copy(center);camera.position.copy(center).addScaledVector(direction,Math.max(10,size*1.35));}}
 controls.update();dirty=true;
}
document.getElementById('module').onchange=()=>{applyView();focusModule();};
function preset(kind){focusModule();const target=controls.target.clone(),distance=camera.position.distanceTo(target);const direction=kind==='top'?new THREE.Vector3(.001,1,.002):kind==='rear'?new THREE.Vector3(0,.4,-1):kind==='side'?new THREE.Vector3(1,.4,0):new THREE.Vector3(.08,.5,1);camera.position.copy(target).addScaledVector(direction.normalize(),distance);controls.update();dirty=true;}

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
 const selected=document.getElementById('module').value;const top=Math.abs(camera.position.clone().sub(controls.target).normalize().y)>.94;
 dimensionLayer.visible=document.getElementById('dimensions').checked;rulerLayer.visible=document.getElementById('ruler').checked;
 for(const group of [...dimensionGroups,...rulerGroups])group.visible=group.userData.module===selected&&(!group.userData.vertical||!top)&&(!group.userData.label?.startsWith('床')||document.getElementById('furniture').checked);
}
function modulePreset(kind){
 const selected=document.getElementById('module').value,anchor=(file===asset.primaryModel)?measurements.anchors[selected]:null;
 if(!anchor){preset(kind);return;}
 const center=point(anchor.center),front=point(anchor.front).sub(center).normalize(),right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),front).normalize();controls.target.copy(center);
 if(kind==='top')camera.position.copy(center).add(new THREE.Vector3(.001,anchor.size*1.9,.002));
 else{const direction=kind==='rear'?front.clone().negate():kind==='side'?right:front;camera.position.copy(center).addScaledVector(direction,anchor.size*1.5).add(new THREE.Vector3(0,anchor.size*.65,0));}
 controls.update();dirty=true;
}
for(const id of ['reset','front','top','rear','side'])document.getElementById(id).onclick=()=>modulePreset(id);
for(const id of ['dimensions','ruler','furniture'])document.getElementById(id).onchange=()=>{applyView();updateMeasurementLayers();};
const sample=document.getElementById('bedSample');sample.onclick=()=>{
 document.getElementById('module').value='M01';document.getElementById('floor').value='1';document.getElementById('furniture').checked=true;document.getElementById('dimensions').checked=true;section=true;applyView();setLighting(false);modulePreset('top');updateMeasurementLayers();
};

document.getElementById('windowView').onclick=()=>{document.getElementById('module').value='M01';document.getElementById('floor').value='1';document.getElementById('glass').checked=true;document.getElementById('dimensions').checked=false;section=false;applyView();setLighting(true);const v=measurements.furniture_window_view;camera.position.copy(point(v.eye));controls.target.copy(point(v.target));controls.update();dirty=true;};

function sampleView(outside){document.getElementById('module').value='M01';document.getElementById('floor').value='1';document.getElementById('dimensions').checked=false;document.getElementById('furniture').checked=true;section=!outside;applyView();setLighting(false);const v=outside?measurements.sample_window:measurements.sample_view;camera.position.copy(point(v.eye));controls.target.copy(point(v.target));controls.update();dirty=true;}
document.getElementById('nookClose').onclick=()=>sampleView(false);
document.getElementById('nookWindow').onclick=()=>sampleView(true);
for(const [id,factor] of [['zoomIn',.8],['zoomOut',1.25]])document.getElementById(id).onclick=()=>{const offset=camera.position.clone().sub(controls.target);offset.setLength(Math.min(controls.maxDistance,Math.max(controls.minDistance,offset.length()*factor)));camera.position.copy(controls.target).add(offset);controls.update();dirty=true;};
document.getElementById('download').disabled=false;document.getElementById('download').onclick=()=>{const url=URL.createObjectURL(new Blob([buffer],{type:'model/gltf-binary'}));const a=document.createElement('a');a.href=url;a.download=file.split('/').pop();a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();dirty=true;}
new ResizeObserver(resize).observe(stage);resize();
for(const option of document.getElementById('module').options)if(option.value!=='all')option.disabled=!asset.modes.includes(option.value)||file!==asset.primaryModel;
for(const id of ['bedSample','nookClose','nookWindow','windowView'])document.getElementById(id).hidden=!(measurements.sample_view&&measurements.sample_window&&measurements.furniture_window_view&&file===asset.primaryModel);
if(!estate){ground.geometry.dispose();ground.geometry=new THREE.CircleGeometry(modelRadius*2.5,128);ground.position.set(modelCenter.x,modelBounds.min.y-.01,modelCenter.z);controls.minDistance=modelRadius*.12;controls.maxDistance=modelRadius*20;camera.near=Math.max(.001,modelRadius/500);camera.far=modelRadius*150;camera.updateProjectionMatrix();}
applyView();focusModule();updateMeasurementLayers();
function animate(){requestAnimationFrame(animate);const moved=controls.update();if(moved||dirty){updateMeasurementLayers();renderer.render(scene,camera);dirty=false;}}
animate();
window.elfiePreview={ready:true,meshCount:meshes.length,triangleCount,source:file,state:()=>({section,floor:document.getElementById('floor').value,camera:camera.position.toArray(),visible:meshes.filter(m=>m.visible).length,references:meshes.filter(m=>m.visible&&m.userData.reference).length,furniture:meshes.filter(m=>m.visible&&m.userData.furniture).length,dimensionLabels:dimensionGroups.filter(g=>g.visible&&dimensionLayer.visible).map(g=>g.userData.label),rulerGroups:rulerGroups.filter(g=>g.visible&&rulerLayer.visible).length})};
}catch(e){status.textContent='载入失败';error.style.display='block';error.textContent='预览没有成功载入：'+e.message+'。请使用支持 WebGL 的新版 Chrome、Edge 或 Safari 打开此文件。';console.error(e);}
