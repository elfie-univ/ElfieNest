import * as THREE from '/assets/design/library/three.module.js';

// Preview detail is disposable. Saved models, material values and light fixtures
// remain authoritative; close-up views and shadow updates use the original mesh.
export function detailJob(geometry){
 const position=geometry.attributes.position;
 const attributes=Object.entries(geometry.attributes).filter(([name])=>name!=='position');
 const stride=attributes.reduce((sum,[,a])=>sum+a.itemSize,0),values=new Float32Array(position.count*stride);
 let offset=0;
 for(let i=0;i<position.count;i++)for(const [,a]of attributes)for(let c=0;c<a.itemSize;c++)values[offset++]=a.getComponent(i,c);
 const positions=new Float32Array(position.count*3);
 for(let i=0;i<position.count;i++)positions.set([position.getX(i),position.getY(i),position.getZ(i)],i*3);
 return {positions,attributes:values,stride,weights:attributes.flatMap(([name,a])=>Array(a.itemSize).fill(name==='normal'?.1:1)),indices:geometry.index.array.slice()};
}
export function simplifyDetail(job,simplifier){
 const scale=simplifier.getScale(job.positions,3);
 if(!scale)return {indices:job.indices,error:0};
 const [indices,error]=simplifier.simplifyWithAttributes(job.indices,job.positions,3,job.attributes,job.stride,job.weights,null,Math.floor(job.indices.length*.5/3)*3,.0005/scale,['LockBorder']);
 return {indices,error:error*scale};
}
function eligible(mesh){
 const g=mesh.geometry,materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
 return !mesh.isInstancedMesh&&!mesh.isSkinnedMesh&&!mesh.morphTargetInfluences&&!mesh.userData.glass
  &&!mesh.userData.lighting_diffuser&&!mesh.userData.design_lights?.length
  &&!Object.keys(g.morphAttributes).length&&g.index?.count>=6000&&g.groups.length<=1
  &&Object.keys(g.attributes).every(k=>['position','normal','uv','color'].includes(k))
  &&materials.every(m=>!m.transparent&&!m.transmission&&!m.emissive?.getHex());
}
function mipBytes(width,height){let n=width*height*4;while(width>1||height>1){width=Math.max(1,width>>1);height=Math.max(1,height>>1);n+=width*height*4;}return n;}
function imageHalf(image,width,height){
 const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
 const context=canvas.getContext('2d');context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';context.drawImage(image,0,0,width,height);return canvas;
}
export function createAdaptiveDetail(meshes,{makeImage=imageHalf}={}){
 const records=new Map(),textures=new Map(),bounds=new Map(),position=new THREE.Vector3(),transmission=[];let closed=false,transmissionScale=1;
 const excluded=new Set(meshes.filter(mesh=>!eligible(mesh)).map(mesh=>mesh.geometry));
 const protectedSources=new Set();
 for(const mesh of meshes)for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material])for(const [key,texture]of Object.entries(material))
  if(texture?.isTexture&&(key!=='map'||material.transparent||material.alphaTest||material.emissive?.getHex()))protectedSources.add(texture.source);
 for(const mesh of meshes){
  if(!mesh.geometry.boundingSphere)mesh.geometry.computeBoundingSphere();
  bounds.set(mesh,mesh.geometry.boundingSphere.clone().applyMatrix4(mesh.matrixWorld));
  if(!excluded.has(mesh.geometry)){
   if(!records.has(mesh.geometry))records.set(mesh.geometry,{original:mesh.geometry.index,meshes:[],low:null,error:0});
   records.get(mesh.geometry).meshes.push(mesh);
  }
  for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material]){
   if(material.transmission>0)transmission.push(mesh);
   // Keep alpha, emissive/light and physical-effect maps at their original size.
   const texture=material.map,image=texture?.source.data;
   if(!texture||protectedSources.has(texture.source)||!image?.width||Math.min(image.width,image.height)<1024||!texture.generateMipmaps
    ||texture.format!==THREE.RGBAFormat||texture.type!==THREE.UnsignedByteType
    ||material.transparent||material.alphaTest||material.emissive?.getHex()||texture.repeat.length()>3)continue;
   if(!textures.has(texture.source))textures.set(texture.source,{original:texture.source,low:null,textures:new Set(),meshes:new Set(),saved:mipBytes(image.width,image.height)-mipBytes(Math.max(1,image.width>>1),Math.max(1,image.height>>1))});
   const record=textures.get(texture.source);record.textures.add(texture);record.meshes.add(mesh);
  }
 }
 function visible(mesh){for(let p=mesh;p;p=p.parent)if(!p.visible)return false;return true;}
 function distance(mesh){const sphere=bounds.get(mesh);return Math.max(.001,position.distanceTo(sphere.center)-sphere.radius);}
 function update(camera,height,{fullDetail=false,fullTextures=fullDetail}={}){
  if(closed)return false;camera.getWorldPosition(position);const pixels=height/(2*Math.tan(camera.fov*Math.PI/360));let changed=false;
  const previousScale=transmissionScale;
  transmissionScale=fullDetail||transmission.some(mesh=>visible(mesh)&&2*bounds.get(mesh).radius*pixels/distance(mesh)>256)?1:.5;
  changed ||= previousScale!==transmissionScale;
  for(const [geometry,record]of records){
   if(!record.low)continue;
   const near=fullDetail||record.meshes.some(mesh=>visible(mesh)&&((Array.isArray(mesh.material)?mesh.material:[mesh.material]).some(m=>m.clippingPlanes?.length)||record.error*mesh.matrixWorld.getMaxScaleOnAxis()*pixels/distance(mesh)>(geometry.index===record.low?.18:.12)));
   const index=near?record.original:record.low;
   if(geometry.index!==index){geometry.setIndex(index);changed=true;}
  }
  for(const record of textures.values()){
   const image=record.original.data;
   const far=!fullTextures&&[...record.meshes].every(mesh=>!visible(mesh)||2*bounds.get(mesh).radius*pixels/distance(mesh)<Math.min(image.width,image.height)/(record.low&&[...record.textures].some(t=>t.source===record.low)?3:4));
   if(far&&!record.low)record.low=new THREE.TextureSource(makeImage(image,Math.max(1,image.width>>1),Math.max(1,image.height>>1)));
   const source=far?record.low:record.original;
   for(const texture of record.textures)if(texture.source!==source){texture.dispose();texture.source=source;texture.needsUpdate=true;changed=true;}
  }
  return changed;
 }
 function stats(){let reduced=0,saved=0,geometries=0,bytes=0;for(const [geometry,r]of records)if(r.low){geometries++;bytes+=r.low.array.byteLength;if(geometry.index===r.low)for(const mesh of r.meshes)if(visible(mesh))reduced+=(r.original.count-r.low.count)/3;}
  for(const r of textures.values())if(r.low&&[...r.textures].some(t=>t.source===r.low))saved+=r.saved;
  return {geometries,reducedTriangles:reduced,extraIndexBytes:bytes,textureBytesSaved:saved,transmissionScale};
 }
 function accept(geometry,result){
  if(closed)return;const record=records.get(geometry);
  if(!record||result.error>.000501||!Number.isFinite(result.error)||result.indices.length>=record.original.count*.95)return;
  record.low=new THREE.BufferAttribute(new record.original.array.constructor(result.indices),1);record.error=result.error;
 }
 function dispose(){if(closed)return;for(const [geometry,r]of records)geometry.setIndex(r.original);for(const r of textures.values())for(const texture of r.textures)if(texture.source!==r.original){texture.dispose();texture.source=r.original;texture.needsUpdate=true;}records.clear();textures.clear();bounds.clear();closed=true;}
 return {jobs:()=>[...records.keys()],accept,update,stats,dispose,transmissionScale:()=>transmissionScale};
}

// Geometry reduction stays off the UI thread and begins after the first frame.
// The worker receives copies; transferring its buffers cannot detach saved inputs.
export async function prepareAdaptiveDetail(detail,{workerURL,onChange=()=>{},signal}={}){
 function workerMain(){let simplify,ready;self.onmessage=async({data})=>{try{if(data.url){ready=import(data.url).then(async module=>{await module.MeshoptSimplifier.ready;simplify=module.MeshoptSimplifier;});await ready;self.postMessage({ready:true});return;}await ready;const job=data.job,scale=simplify.getScale(job.positions,3);const [indices,error]=scale?simplify.simplifyWithAttributes(job.indices,job.positions,3,job.attributes,job.stride,job.weights,null,Math.floor(job.indices.length*.5/3)*3,.0005/scale,['LockBorder']):[job.indices,0];self.postMessage({indices,error:error*scale},[indices.buffer]);}catch(error){self.postMessage({error:error.message});}};}
 const url=URL.createObjectURL(new Blob([`(${workerMain.toString()})()`],{type:'text/javascript'})),worker=new Worker(url);URL.revokeObjectURL(url);
 const stop=()=>worker.terminate();signal?.addEventListener('abort',stop,{once:true});
 function request(data,transfer=[]){return new Promise((resolve,reject)=>{if(signal?.aborted){reject(new DOMException('Preview closed','AbortError'));return;}const abort=()=>{cleanup();reject(new DOMException('Preview closed','AbortError'));};const cleanup=()=>{signal?.removeEventListener('abort',abort);worker.onmessage=null;worker.onerror=null;};worker.onmessage=({data})=>{cleanup();typeof data.error==='string'?reject(new Error(data.error)):resolve(data);};worker.onerror=event=>{cleanup();reject(new Error(event.message));};signal?.addEventListener('abort',abort,{once:true});worker.postMessage(data,transfer);});}
 try{await request({url:workerURL});for(const geometry of detail.jobs()){if(signal?.aborted)break;const job=detailJob(geometry),result=await request({job},[job.positions.buffer,job.attributes.buffer,job.indices.buffer]);detail.accept(geometry,result);}onChange();}finally{signal?.removeEventListener('abort',stop);worker.terminate();}
}
