import * as THREE from '/assets/design/library/three.module.js';
import {GLTFLoader} from '/assets/design/library/GLTFLoader.js';
import {sceneMeshSelection,subsetGLB,placementTransforms,sceneReferenceLayer} from './design-state.mjs';

export async function loadDesignScene(plan,fileURL){
 const model=new THREE.Group(),sources=new Map(),claimedReferences=new Set();
 for(const layer of plan.layers){
  if(sources.has(layer.file))continue;
  const response=await fetch(fileURL(layer.file));
  if(!response.ok)throw new Error('组合源文件无法读取');
  const buffer=await response.arrayBuffer();
  const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))].map(n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==layer.digest)throw new Error('组合源文件已改变，请刷新');
  const length=new DataView(buffer).getUint32(12,true);
  const doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,length)));
  const layers=plan.layers.filter(l=>l.file===layer.file);
  const helpers=sceneReferenceLayer(doc,layers,claimedReferences);
  const selected=new Set([...layers.flatMap(l=>l.nodes),...helpers.nodes]);
  const gltf=await new Promise((resolve,reject)=>new GLTFLoader().parse(subsetGLB(buffer,selected),fileURL(layer.file).replace(/[^/]*$/,''),resolve,reject));
  sources.set(layer.file,{gltf,doc,helpers});
 }
 for(const [file,{gltf,doc,helpers}] of sources){
  const layers=plan.layers.filter(l=>l.file===file),normal=[];
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
    let properties={};const ancestry=[];
    for(let o=original;o;o=o.parent)ancestry.unshift(o.userData);
    for(const data of ancestry)properties={...properties,...data};
    mesh.userData={...properties,designLayer:true,designReference:layer.reference,
     designEditable:!layer.reference,designObject:layer.object,
     module:job.module||properties.module||layer.module||undefined,floor:properties.floor||layer.floor||1,
     furniture:layer.group==='layout'||layer.group==='part'||layer.group==='kit'||!!properties.furniture};
   });
   for(const mesh of copies.reverse())if(mesh.userData.designExcluded&&!mesh.children.length)mesh.removeFromParent();
   copy.applyMatrix4(job.matrix);model.add(copy);
  }
 }
 return model;
}
