import * as THREE from '/assets/design/library/three.module.js';
import {GLTFLoader} from '/assets/design/library/GLTFLoader.js';
import {sceneMeshSelection,subsetGLB,placementTransforms,sceneReferenceLayer} from './design-state.mjs';

// Match the renderer's upload parameters; UV transforms stay on each Texture.
function textureUploadKey(texture){
 return JSON.stringify([texture.wrapS,texture.wrapT,texture.wrapR||0,texture.magFilter,
  texture.minFilter,texture.anisotropy,texture.internalFormat,texture.format,texture.type,
  texture.generateMipmaps,texture.premultiplyAlpha,texture.flipY,texture.unpackAlignment,texture.colorSpace]);
}
function textureMemory(textures){
 const sources=new Set(),uploads=new Map(),images=new Set();let uploadBytes=0,decodedBytes=0,uploadCount=0;
 for(const texture of textures){
  const source=texture.source,image=source.data;sources.add(source);
  if(!images.has(image)){images.add(image);decodedBytes+=(image?.width||0)*(image?.height||0)*4;}
  if(!uploads.has(source))uploads.set(source,new Set());
  const keys=uploads.get(source),key=textureUploadKey(texture);if(keys.has(key))continue;
  keys.add(key);uploadCount++;
  if(texture.format!==THREE.RGBAFormat||texture.type!==THREE.UnsignedByteType)continue;
  let w=image?.width||0,h=image?.height||0;if(!w||!h)continue;
  uploadBytes+=w*h*4;
  if(texture.generateMipmaps)while(w>1||h>1){w=Math.max(1,Math.floor(w/2));h=Math.max(1,Math.floor(h/2));uploadBytes+=w*h*4;}
 }
 return {sources:sources.size,uploadCount,uploadBytes,decodedBytes};
}
export async function shareLoadedTextures(model,sources){
 const identities=new Map();
 for(const {gltf,doc} of sources.values()){
  const parser=gltf.parser,images=new Map();
  for(const [texture,reference]of parser.associations){
   if(!texture.isTexture||!Number.isInteger(reference.textures))continue;
   const definition=doc.textures?.[reference.textures];
   if(!definition||definition.extensions)continue;
   const index=definition.source,image=doc.images?.[index];if(!image)continue;
   if(!images.has(index))images.set(index,(async()=>{
    const external=image.uri?.match(/(?:^|\/)([a-f0-9]{64})\.(png|jpg)$/);
    if(external)return `${image.mimeType||(external[2]==='png'?'image/png':'image/jpeg')}:${external[1]}`;
    if(image.bufferView!==undefined){
     const bytes=await parser.getDependency('bufferView',image.bufferView);
     const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
     return `${image.mimeType}:${hash}`;
    }
    return null;
   })());
   const identity=await images.get(index);if(identity)identities.set(texture.source,identity);
  }
 }
 const textures=new Set();
 model.traverse(mesh=>{
  if(!mesh.isMesh)return;
  for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material])
   for(const value of Object.values(material))if(value?.isTexture)textures.add(value);
 });
 const before=textureMemory(textures),shared=new Map();
 for(const texture of textures){
  const identity=identities.get(texture.source);if(!identity)continue;
  const key=identity+':'+textureUploadKey(texture);
  if(shared.has(key))texture.source=shared.get(key);else shared.set(key,texture.source);
 }
 const after=textureMemory(textures);
 return {textureObjects:textures.size,sourcesBefore:before.sources,sourcesAfter:after.sources,
  gpuUploadsBefore:before.uploadCount,gpuUploadsAfter:after.uploadCount,
  uploadBytesBefore:before.uploadBytes,uploadBytesAfter:after.uploadBytes,
  decodedBytesBefore:before.decodedBytes,decodedBytesAfter:after.decodedBytes};
}

// Batch identical static opaque draws within one room and floor. Source nodes
// remain independent for filtering, measurements and their attached lights.
export function batchStaticMeshes(meshes,scene){
 const groups=new Map(),batches=[],members=new Map();
 scene.updateMatrixWorld(true);
 for(const mesh of meshes){
  const material=mesh.material,m=mesh.matrixWorld;
  if(!mesh.isMesh||mesh.isInstancedMesh||mesh.isSkinnedMesh||mesh.morphTargetInfluences
   ||Object.keys(mesh.geometry.morphAttributes).length||Array.isArray(material)
   ||material.transparent||material.transmission||material.clippingPlanes?.length
   ||mesh.userData.full_height||mesh.layers.mask!==1||!Number.isFinite(m.determinant())||m.determinant()===0
   ||mesh.onBeforeRender!==THREE.Mesh.prototype.onBeforeRender
   ||mesh.onAfterRender!==THREE.Mesh.prototype.onAfterRender)continue;
  const axes=[0,1,2].map(i=>new THREE.Vector3().setFromMatrixColumn(m,i));
  if(axes.some(a=>!Number.isFinite(a.lengthSq())||a.lengthSq()===0))continue;
  // Exported Float32 matrices carry small orthogonality roundoff. Keep their
  // positions unchanged, allowing only a microradian-scale normal discrepancy.
  if(axes.some((a,i)=>axes.some((b,j)=>i!==j&&Math.abs(a.dot(b))>1e-6*a.length()*b.length())))continue;
  const key=JSON.stringify([mesh.geometry.uuid,material.uuid,mesh.userData.module,mesh.userData.floor,
   mesh.castShadow,mesh.receiveShadow,mesh.renderOrder,m.determinant()<0]);
  if(!groups.has(key))groups.set(key,[]);groups.get(key).push(mesh);
 }
 for(const group of groups.values()){
  if(group.length<2)continue;
  const first=group[0],batch=new THREE.InstancedMesh(first.geometry,first.material,group.length);
  // Put reflection on the batch object, where Three flips face winding. Every
  // instance matrix stays positive; mirrored furniture keeps its exact placement.
  if(first.matrixWorld.determinant()*scene.matrixWorld.determinant()<0)batch.scale.x=-1;
  batch.castShadow=first.castShadow;batch.receiveShadow=first.receiveShadow;batch.renderOrder=first.renderOrder;
  batch.name='Static preview batch';scene.add(batch);batches.push(batch);members.set(batch,group);
 }
 let motion=false;
 function sync(enabled=true,{camera=null}={}){
  scene.updateMatrixWorld(true);
  let frustum=null;
  if(camera){
   camera.updateMatrixWorld(true);
   frustum=new THREE.Frustum().setFromProjectionMatrix(
    new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse));
  }
  const inverse=new THREE.Matrix4(),matrix=new THREE.Matrix4();
  for(const batch of batches){
   inverse.copy(batch.matrixWorld).invert();
   let count=0;
   for(const mesh of members.get(batch)){
    if(enabled)mesh.layers.disable(0);else mesh.layers.enable(0);
    let visible=mesh.visible;
    for(let p=mesh.parent;p&&visible;p=p.parent)visible=p.visible;
    if(enabled&&visible&&(!frustum||frustum.intersectsObject(mesh)))batch.setMatrixAt(count++,matrix.multiplyMatrices(inverse,mesh.matrixWorld));
   }
   batch.count=motion?Math.min(count,2):count;batch.visible=batch.count>0;
   if(count){batch.instanceMatrix.needsUpdate=true;batch.computeBoundingBox();batch.computeBoundingSphere();}
  }
 }
 function setMotion(active){
  if(motion===active)return false;
  motion=active;
  if(active){for(const batch of batches)batch.count=Math.min(batch.count,2);}
  else sync();
  return true;
 }
 return {batches,sync,setMotion};
}

function meshProperties(properties,layer,job){
 return {...properties,designLayer:true,designReference:layer.reference,
  designEditable:!layer.reference,designObject:layer.object,
  module:job.module||properties.module||layer.module||undefined,floor:properties.floor||layer.floor||1,
  furniture:layer.group==='layout'||layer.group==='part'||layer.group==='kit'||!!properties.furniture};
}
function inheritedProperties(object){
 const ancestry=[];for(let o=object;o;o=o.parent)ancestry.unshift(o.userData);
 return Object.assign({},...ancestry);
}
async function addTemplateInstances(copy,layer,job,host,sources){
 for(const instance of layer.templateInstances||[]){
  const template=sources.get(instance.file)?.gltf;
  if(!template)throw new Error('公共家具母版无法读取');
  template.scene.updateMatrixWorld(true);
  for(const binding of instance.bindings){
   if(!Array.isArray(binding.matrix)||binding.matrix.length!==16||!binding.matrix.every(Number.isFinite))throw new Error('公共家具摆放矩阵无效');
   const primitives=[];
   template.scene.traverse(mesh=>{
    if(!mesh.isMesh)return;
    for(let node=mesh;node;node=node.parent){
     const index=template.parser.associations.get(node)?.nodes;
     if(index===undefined)continue;
     if(index===binding.node)primitives.push({mesh,node});
     break;
    }
   });
   if(!primitives.length)throw new Error('公共家具母版节点缺失');
   for(const {mesh:original,node} of primitives){
    const mesh=original.clone(false),primitive=template.parser.associations.get(original)?.primitives;
    if(binding.materials){
     const indexes=Array.isArray(mesh.material)?mesh.material.map((_,i)=>binding.materials[i]):[binding.materials[primitive??0]];
     const originals=Array.isArray(mesh.material)?mesh.material:[mesh.material];
     const materials=[];
     for(const [i,index] of indexes.entries()){
      if(index===null){materials.push(originals[i]);continue;}
      if(!Number.isInteger(index)||index<0)throw new Error('公共家具材质绑定缺失');
      mesh.material=await host.parser.getDependency('material',index);
      host.parser.assignFinalMaterial(mesh);
      materials.push(mesh.material);
     }
     mesh.material=Array.isArray(mesh.material)?materials:materials[0];
    }
    // Bindings map the template node's local geometry into the host world. Strip the
    // template's saved placement, retaining only transforms below that node.
    mesh.matrixAutoUpdate=false;
    mesh.matrix.fromArray(binding.matrix).multiply(node.matrixWorld.clone().invert().multiply(original.matrixWorld));
    mesh.userData=meshProperties({...binding.properties,
     designTemplate:instance.object,designTemplateInstance:instance.id},layer,job);
    copy.add(mesh);
   }
  }
 }
}
export async function loadDesignScene(plan,fileURL){
 const model=new THREE.Group(),sources=new Map(),requests=new Map(),claimedReferences=new Set();
 const request=(item,host=false)=>{
  const previous=requests.get(item.file);
  if(previous&&previous.digest!==item.digest)throw new Error('组合源文件版本冲突，请刷新');
  const entry=previous||{file:item.file,digest:item.digest,selected:new Set(),host:false};
  for(const node of item.nodes||[])entry.selected.add(node);
  entry.host ||= host;requests.set(item.file,entry);
 };
 for(const layer of plan.layers){request(layer,true);for(const instance of layer.templateInstances||[])request(instance);}
 const entries=[...requests.values()],buffers=new Map();let next=0;
 async function download(){
 while(next<entries.length){
  const entry=entries[next++];
  const response=await fetch(fileURL(entry.file));
  if(!response.ok)throw new Error('组合源文件无法读取');
  const buffer=await response.arrayBuffer();
  const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))].map(n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==entry.digest)throw new Error('组合源文件已改变，请刷新');
  buffers.set(entry.file,buffer);
 }
 }
 await Promise.all(Array.from({length:Math.min(4,entries.length)},download));
 // Claim shared references in catalog order before independent loaders overlap.
 const jobs=[];
 for(const entry of entries){
  const buffer=buffers.get(entry.file);buffers.delete(entry.file);
  const length=new DataView(buffer).getUint32(12,true);
  const doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,length)));
  const layers=plan.layers.filter(l=>l.file===entry.file);
  const helpers=entry.host?sceneReferenceLayer(doc,layers,claimedReferences):{nodes:[]};
  const selected=new Set([...entry.selected,...helpers.nodes]);
  jobs.push({entry,buffer:subsetGLB(buffer,selected),doc,helpers});
 }
 next=0;
 const parsed=new Map();
 async function parse(){
  while(next<jobs.length){
   const {entry,buffer,doc,helpers}=jobs[next++];
   const gltf=await new Promise((resolve,reject)=>new GLTFLoader().parse(buffer,fileURL(entry.file).replace(/[^/]*$/,''),resolve,reject));
   parsed.set(entry.file,{gltf,doc,helpers});
  }
 }
 await Promise.all(Array.from({length:Math.min(2,jobs.length)},parse));
 for(const entry of entries)sources.set(entry.file,parsed.get(entry.file));
 for(const [file,{gltf,doc,helpers}] of sources){
  const layers=plan.layers.filter(l=>l.file===file),normal=[];
  if(!layers.length)continue;
  if(helpers.nodes.length)normal.push(helpers);
  const jobs=[];
  for(const layer of layers){
   if(Object.keys(layer.placements||{}).length){
    for(const placement of placementTransforms(doc,layer.placements,THREE))jobs.push({layers:[layer],...placement});
   }else normal.push(layer);
  }
  if(normal.length)jobs.push({layers:normal,module:null,matrix:new THREE.Matrix4()});
  for(const job of jobs){
   const owners=new Map();for(const layer of [...job.layers].sort((a,b)=>(a.group==='helper')-(b.group==='helper')))for(const node of layer.nodes)owners.set(node,layer);
   const selected=new Set(owners.keys()),source=gltf.scene,copy=source.clone(true);
   const originals=[],copies=[];source.traverse(o=>originals.push(o));copy.traverse(o=>copies.push(o));
   copies.forEach((mesh,i)=>{
    if(mesh.isLight)mesh.visible=false;
    if(!mesh.isMesh)return;
    const original=originals[i];
    if(!sceneMeshSelection(original,gltf.parser.associations,selected)){
     mesh.geometry=new THREE.BufferGeometry();mesh.userData={designExcluded:true};return;
    }
    let layer;for(let o=original;o;o=o.parent){const node=gltf.parser.associations.get(o)?.nodes;if(node!==undefined){layer=owners.get(node);break;}}
    mesh.userData=meshProperties(inheritedProperties(original),layer,job);
   });
   for(const mesh of copies.reverse())if(mesh.userData.designExcluded&&!mesh.children.length)mesh.removeFromParent();
   for(const layer of job.layers)await addTemplateInstances(copy,layer,job,gltf,sources);
   copy.applyMatrix4(job.matrix);model.add(copy);
  }
 }
 model.userData.previewTextureSharing=await shareLoadedTextures(model,sources);
 return model;
}
