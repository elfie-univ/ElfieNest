import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';

const root=new URL('../../../',import.meta.url);
const local=path=>new URL(path,root).href;
let source=await readFile(new URL('devtools/asset_design/web/scene-model.mjs',root),'utf8');
source=source.replace("'/assets/design/library/three.module.js'",JSON.stringify(local('devtools/web/node_modules/three/build/three.module.js')))
 .replace("'/assets/design/library/GLTFLoader.js'",JSON.stringify(local('devtools/web/node_modules/three/examples/jsm/loaders/GLTFLoader.js')))
 .replace("'./design-state.mjs'",JSON.stringify(local('devtools/asset_design/web/design-state.mjs')));
const {loadDesignScene}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
if(!globalThis.crypto)globalThis.crypto=webcrypto;
if(!globalThis.ProgressEvent)globalThis.ProgressEvent=class extends Event{constructor(type,init){super(type);Object.assign(this,init);}};
function glb(doc,positions){
 const bytes=positions?Buffer.from(new Float32Array(positions).buffer):null;
 if(bytes)Object.assign(doc,{buffers:[{byteLength:bytes.length}],bufferViews:[{buffer:0,byteLength:bytes.length}],accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[0,0,0],max:[1,1,0]}]});
 const raw=Buffer.from(JSON.stringify({asset:{version:'2.0'},scene:0,...doc}));
 const json=Buffer.alloc(Math.ceil(raw.length/4)*4,32);raw.copy(json);
 const out=Buffer.alloc(20+json.length+(bytes?8+bytes.length:0));
 out.writeUInt32LE(0x46546c67,0);out.writeUInt32LE(2,4);out.writeUInt32LE(out.length,8);
 out.writeUInt32LE(json.length,12);out.writeUInt32LE(0x4e4f534a,16);json.copy(out,20);
 if(bytes){out.writeUInt32LE(bytes.length,20+json.length);out.writeUInt32LE(0x004e4942,24+json.length);bytes.copy(out,28+json.length);}
 return out;
}
async function fixture(run){
 const host=glb({scenes:[{nodes:[0,1]}],nodes:[{translation:[0,0,0]},{translation:[10,0,0]}],materials:[{pbrMetallicRoughness:{baseColorFactor:[1,0,0,1]}},{pbrMetallicRoughness:{baseColorFactor:[0,1,0,1]}}]});
 const template=glb({scenes:[{nodes:[0]}],nodes:[{translation:[100,0,0],children:[1]},{mesh:0,translation:[20,0,0]}],meshes:[{primitives:[{attributes:{POSITION:0,COLOR_0:0}},{attributes:{POSITION:0,COLOR_0:0}}]}]},[0,0,0,1,0,0,0,1,0]);
 const files={host,template},requests=[];
 const digest=async b=>Buffer.from(await crypto.subtle.digest('SHA-256',b)).toString('hex');
 const original=globalThis.fetch;
 globalThis.fetch=async url=>{const name=new URL(url).pathname.slice(1);requests.push(name);return new Response(files[name],{status:files[name]?200:404});};
 try{await run({host,template,requests,digest,files});}finally{globalThis.fetch=original;}
}
test('template GLBs load once, retain shared geometry, host colors and room placements',async()=>fixture(async({host,template,requests,digest})=>{
 const binding=x=>({node:1,matrix:[1,0,0,0,0,1,0,0,0,0,1,0,x,2,3,1],materials:[0,1],properties:{floor:2,furniture:true}});
 const layer={file:'host',digest:await digest(host),nodes:[],object:'layout:pod',group:'layout',placements:{M01:0,M02:1},templateInstances:[
  {id:'a',object:'part:chair',file:'template',digest:await digest(template),nodes:[1],bindings:[binding(3)]},
  {id:'b',object:'part:chair',file:'template',digest:await digest(template),nodes:[1],bindings:[binding(6)]},
 ]};
 const model=await loadDesignScene({layers:[layer]},file=>`https://assets.test/${file}`);
 model.updateMatrixWorld(true);const meshes=[];model.traverse(o=>{if(o.isMesh)meshes.push(o);});
 assert.equal(meshes.length,8);assert.equal(requests.filter(f=>f==='template').length,1);
 assert.equal(meshes[0].geometry,meshes[2].geometry);
 assert.deepEqual(meshes.slice(0,2).map(m=>m.material.color.toArray()),[[1,0,0],[0,1,0]]);
 assert.ok(meshes.every(m=>m.material.flatShading));
 assert.ok(meshes.every(m=>m.material.vertexColors));
 assert.ok(meshes.every(m=>m.material.normalScale.y===-1));
 assert.deepEqual(meshes.map(m=>m.matrixWorld.elements[12]),[3,3,6,6,13,13,16,16]);
 assert.deepEqual(meshes.map(m=>m.userData.module),['M01','M01','M01','M01','M02','M02','M02','M02']);
 assert.ok(meshes.every(m=>m.userData.designObject==='layout:pod'&&m.userData.designTemplate==='part:chair'&&m.userData.floor===2));
}));
test('changed or missing template fails without copied geometry fallback',async()=>fixture(async({host,template,digest,files})=>{
 const plan={layers:[{file:'host',digest:await digest(host),nodes:[],object:'layout:pod',group:'layout',templateInstances:[{object:'part:chair',file:'template',digest:'invalid',nodes:[1],bindings:[]}]}]};
 await assert.rejects(loadDesignScene(plan,f=>`https://assets.test/${f}`),/已改变/);
 delete files.template;
 await assert.rejects(loadDesignScene(plan,f=>`https://assets.test/${f}`),/无法读取/);
}));
test('host geometry and reference metadata remain alongside dynamic furniture',async()=>fixture(async({template,digest,files})=>{
 files.host=glb({scenes:[{nodes:[0]}],nodes:[{mesh:0,translation:[7,0,0],extras:{floor:3}}],meshes:[{primitives:[{attributes:{POSITION:0},material:0}]}],materials:[{pbrMetallicRoughness:{baseColorFactor:[1,0,0,1]}}]},[0,0,0,1,0,0,0,1,0]);
 const layer={file:'host',digest:await digest(files.host),nodes:[0],object:'layout:central:3',group:'layout',reference:true,templateInstances:[
  {id:'chair',object:'part:chair',file:'template',digest:await digest(template),nodes:[1],bindings:[{node:1,matrix:[1,0,0,0,0,1,0,0,0,0,1,0,4,0,0,1],materials:[null,null],properties:{floor:3}}]},
 ]};
 const model=await loadDesignScene({layers:[layer]},f=>`https://assets.test/${f}`);
 model.updateMatrixWorld(true);const meshes=[];model.traverse(o=>{if(o.isMesh)meshes.push(o);});
 assert.equal(meshes.length,3);assert.equal(meshes[0].matrixWorld.elements[12],7);
 assert.ok(meshes.every(m=>m.userData.designReference&&!m.userData.designEditable&&m.userData.floor===3));
 layer.templateInstances[0].bindings[0].node=999;
 await assert.rejects(loadDesignScene({layers:[layer]},f=>`https://assets.test/${f}`),/节点缺失/);
}));
test('conflicting template digests cannot silently reuse another revision',async()=>fixture(async({host,template,digest,requests})=>{
 const instance={file:'template',digest:await digest(template),nodes:[1],bindings:[]};
 const plan={layers:[{file:'host',digest:await digest(host),nodes:[],templateInstances:[instance,{...instance,digest:'another-revision'}]}]};
 await assert.rejects(loadDesignScene(plan,f=>`https://assets.test/${f}`),/版本冲突/);
 assert.deepEqual(requests,[]);
}));
test('template metadata never overrides architectural host semantics',async()=>fixture(async({host,digest,files})=>{
 files.template=glb({scenes:[{nodes:[0]}],nodes:[{mesh:0,extras:{furniture:true,role:'furniture',module:'template-room',floor:1}}],meshes:[{primitives:[{attributes:{POSITION:0}}]}]},[0,0,0,1,0,0,0,1,0]);
 const layer={file:'host',digest:await digest(host),nodes:[],object:'building:central',group:'building',module:'central',floor:2,templateInstances:[
  {id:'architectural-fern',object:'part:fern',file:'template',digest:await digest(files.template),nodes:[0],bindings:[{node:0,matrix:[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],properties:{floor:2}}]},
 ]};
 const model=await loadDesignScene({layers:[layer]},f=>`https://assets.test/${f}`);
 const meshes=[];model.traverse(o=>{if(o.isMesh)meshes.push(o);});
 assert.equal(meshes.length,1);
 assert.equal(meshes[0].userData.furniture,false);
 assert.equal(meshes[0].userData.role,undefined);
 assert.equal(meshes[0].userData.module,'central');
 assert.equal(meshes[0].userData.floor,2);
}));
test('model downloads overlap with a bounded queue and retain layer order',async()=>fixture(async({host,digest})=>{
 const original=globalThis.fetch,waiting=[];let active=0,peak=0,released=false;
 globalThis.fetch=async()=>{active++;peak=Math.max(peak,active);if(!released)await new Promise(resolve=>waiting.push(resolve));active--;return new Response(host);};
 const layers=await Promise.all(Array.from({length:7},async(_,i)=>({file:`host${i}`,digest:await digest(host),nodes:[0],object:`building:${i}`,group:'building'})));
 const pending=loadDesignScene({layers},f=>`https://assets.test/${f}`);
 try{
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(waiting.length,4);
  released=true;waiting.splice(0).forEach(resolve=>resolve());
  const model=await pending;assert.equal(model.children.length,7);assert.equal(peak,4);
 }finally{released=true;waiting.splice(0).forEach(resolve=>resolve());await pending.catch(()=>{});globalThis.fetch=original;}
}));
test('independent GLB resource loads overlap while scene layer order stays stable',async()=>{
 const original=globalThis.fetch,waiting=[];let released=false,firstStarted;
 const first=new Promise(resolve=>{firstStarted=resolve;});
 const bytes=Buffer.from(new Float32Array([0,0,0,1,0,0,0,1,0]).buffer);
 const files={};
 for(const name of ['a','b'])files[name]=glb({scenes:[{nodes:[0]}],nodes:[{mesh:0,extras:{module:name}}],meshes:[{primitives:[{attributes:{POSITION:0}}]}],buffers:[{uri:name+'.bin',byteLength:bytes.length}],bufferViews:[{buffer:0,byteLength:bytes.length}],accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[0,0,0],max:[1,1,0]}]});
 const digest=async b=>Buffer.from(await crypto.subtle.digest('SHA-256',b)).toString('hex');
 const layers=await Promise.all(Object.keys(files).map(async name=>({file:name,digest:await digest(files[name]),nodes:[0],object:name,group:'building'})));
 globalThis.fetch=async request=>{const name=new URL(typeof request==='string'?request:request.url).pathname.slice(1);if(name.endsWith('.bin')){if(!released)await new Promise(resolve=>{waiting.push(resolve);firstStarted();});return new Response(bytes);}return new Response(files[name]);};
 const pending=loadDesignScene({layers},f=>`https://assets.test/${f}`);
 try{
  await first;await new Promise(resolve=>setImmediate(resolve));
  assert.equal(waiting.length,2,'both parsers request their independent buffer without waiting for the other scene');
  released=true;waiting.splice(0).forEach(resolve=>resolve());
  const model=await pending;assert.deepEqual(model.children.map(c=>c.children[0].userData.designObject),['a','b']);
 }finally{released=true;waiting.splice(0).forEach(resolve=>resolve());await pending.catch(()=>{});globalThis.fetch=original;}
});

test('static batches retain exact geometry, color, world placement and independent visibility',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {batchStaticMeshes}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const scene=new THREE.Scene(),parent=new THREE.Group();parent.position.x=10;scene.add(parent);
 const geometry=new THREE.BoxGeometry(),material=new THREE.MeshStandardMaterial({color:0x95b58c});
 const meshes=Array.from({length:3},(_,i)=>{const m=new THREE.Mesh(geometry,material);m.position.set(i,2,3);m.userData={module:'M01',floor:1};m.castShadow=true;parent.add(m);return m;});
 const lamp=new THREE.PointLight();meshes[0].add(lamp);scene.updateMatrixWorld(true);
 const before=meshes.map(m=>m.matrixWorld.clone()),batching=batchStaticMeshes(meshes,scene);batching.sync();
 assert.equal(batching.batches.length,1);const batch=batching.batches[0];
 assert.strictEqual(batch.geometry,geometry);assert.strictEqual(batch.material,material);assert.equal(batch.count,3);assert.equal(batch.castShadow,true);
 assert.ok(meshes.every(m=>m.visible&&!m.layers.test(new THREE.Layers())));assert.ok(lamp.layers.test(new THREE.Layers()));
 for(let i=0;i<3;i++){const matrix=new THREE.Matrix4();batch.getMatrixAt(i,matrix);assert.deepEqual(matrix.elements,before[i].elements);}
 meshes[1].visible=false;batching.sync();assert.equal(batch.count,2);assert.equal(batch.boundingBox.max.x,12.5);
 batching.setMotion(true);assert.equal(batch.count,2);batching.setMotion(false);assert.equal(batch.count,2);
 parent.visible=false;batching.sync();assert.equal(batch.visible,false);
 parent.visible=true;batching.sync(false);assert.equal(batch.visible,false);assert.ok(meshes.every(m=>m.layers.test(new THREE.Layers())));
});

test('static batches can cull instances outside the active camera frustum',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {batchStaticMeshes}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const scene=new THREE.Scene(),geometry=new THREE.BoxGeometry(),material=new THREE.MeshStandardMaterial();
 for(const x of [0,100]){const mesh=new THREE.Mesh(geometry,material);mesh.position.x=x;mesh.userData={module:'M01',floor:1};scene.add(mesh);}
 const camera=new THREE.PerspectiveCamera(40,1,.1,50);camera.position.set(0,0,10);camera.lookAt(0,0,0);camera.updateProjectionMatrix();
 const batching=batchStaticMeshes(scene.children,scene);batching.sync(true,{camera});
 assert.equal(batching.batches.length,1);assert.equal(batching.batches[0].count,1);
});

test('batching excludes glass, genuine shear, morphs and clipped shells',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {batchStaticMeshes}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const scene=new THREE.Scene(),geometry=new THREE.BoxGeometry(),material=new THREE.MeshStandardMaterial();
 const variants=[m=>m.material=new THREE.MeshStandardMaterial({transparent:true}),m=>{m.matrixAutoUpdate=false;m.matrix.elements[4]=.2;},m=>m.userData.full_height=true,m=>{m.morphTargetInfluences=[0];},m=>m.userData.floor=2];
 const meshes=variants.flatMap(edit=>Array.from({length:2},()=>{const m=new THREE.Mesh(geometry,material);m.userData={module:'M01',floor:1};edit(m);scene.add(m);return m;}));scene.updateMatrixWorld(true);
 const batching=batchStaticMeshes(meshes,scene);batching.sync();assert.equal(batching.batches.length,1);assert.equal(batching.batches[0].count,2);
 assert.ok(meshes.slice(0,-2).every(m=>m.layers.mask===1));
});

test('identical image content shares GPU sources while texture transforms and material colors stay independent',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {shareLoadedTextures}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const model=new THREE.Group(),sources=new Map(),textures=[];
 for(let i=0;i<2;i++){
  const texture=new THREE.Texture({width:1024,height:1024});texture.colorSpace=THREE.SRGBColorSpace;texture.offset.set(i/4,0);texture.repeat.set(i+1,1);texture.rotation=i*.2;texture.channel=i;
  const material=new THREE.MeshStandardMaterial({map:texture,color:i?0x95b58c:0xd39bae,emissive:0x102030});model.add(new THREE.Mesh(new THREE.BoxGeometry(),material));textures.push(texture);
  sources.set(String(i),{doc:{textures:[{source:0}],images:[{uri:'../resources/'+ 'a'.repeat(64)+'.png'}]},gltf:{parser:{associations:new Map([[texture,{textures:0}]])}}});
 }
 const originalColors=model.children.map(m=>[m.material.color.toArray(),m.material.emissive.toArray()]);
 const stats=await shareLoadedTextures(model,sources);
 assert.strictEqual(textures[0].source,textures[1].source);assert.notStrictEqual(textures[0],textures[1]);
 assert.deepEqual(textures[1].offset.toArray(),[.25,0]);assert.deepEqual(textures[1].repeat.toArray(),[2,1]);assert.equal(textures[1].rotation,.2);assert.equal(textures[1].channel,1);
 assert.deepEqual(model.children.map(m=>[m.material.color.toArray(),m.material.emissive.toArray()]),originalColors);
 assert.equal(stats.sourcesBefore,2);assert.equal(stats.sourcesAfter,1);assert.equal(stats.uploadBytesBefore,stats.uploadBytesAfter*2);
});

test('color space, sampling and upload differences never share texture sources',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {shareLoadedTextures}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const model=new THREE.Group(),sources=new Map(),textures=[];
 const edits=[()=>{},t=>t.colorSpace=THREE.SRGBColorSpace,t=>t.wrapS=THREE.RepeatWrapping,t=>t.minFilter=THREE.NearestFilter,t=>t.flipY=false,t=>t.premultiplyAlpha=true,t=>t.anisotropy=4,t=>t.generateMipmaps=false,t=>t.unpackAlignment=1];
 for(const [i,edit]of edits.entries()){
  const t=new THREE.Texture({width:16,height:16});edit(t);textures.push(t);model.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:t})));
  sources.set(String(i),{doc:{textures:[{source:0}],images:[{uri:'../resources/'+ 'a'.repeat(64)+'.png'}]},gltf:{parser:{associations:new Map([[t,{textures:0}]])}}});
 }
 await shareLoadedTextures(model,sources);assert.equal(new Set(textures.map(t=>t.source)).size,textures.length);
});

test('embedded images and external content-addressed images can share without loading unused textures',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {shareLoadedTextures}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const bytes=new Uint8Array([1,2,3]),hash=Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex'),model=new THREE.Group(),sources=new Map(),textures=[];let reads=0;
 for(let i=0;i<2;i++){
  const t=new THREE.Texture({width:8,height:8});textures.push(t);model.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:t})));
  sources.set(String(i),{doc:{textures:[{source:0},{source:1}],images:[i?{bufferView:4,mimeType:'image/png'}:{uri:hash+'.png'},{}]},gltf:{parser:{associations:new Map([[t,{textures:0}]]),getDependency:async(type,index)=>{assert.equal(type,'bufferView');assert.equal(index,4);reads++;return bytes.buffer;}}}});
 }
 await shareLoadedTextures(model,sources);assert.strictEqual(textures[0].source,textures[1].source);assert.equal(reads,1);
});

test('mirrored static copies batch under a reflected parent with positive instance transforms and exact world placement',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {batchStaticMeshes}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const scene=new THREE.Scene(),geometry=new THREE.BoxGeometry(),material=new THREE.MeshStandardMaterial({side:THREE.DoubleSide});
 const meshes=Array.from({length:3},(_,i)=>{const mesh=new THREE.Mesh(geometry,material);mesh.scale.set(-1,2,1.5);mesh.rotation.y=.4;mesh.position.set(i*3,2,4);mesh.userData={module:'M01',floor:1};scene.add(mesh);return mesh;});scene.updateMatrixWorld(true);
 const before=meshes.map(m=>m.matrixWorld.clone()),batching=batchStaticMeshes(meshes,scene);batching.sync();
 assert.equal(batching.batches.length,1);const batch=batching.batches[0];assert.ok(batch.matrixWorld.determinant()<0);assert.strictEqual(batch.geometry,geometry);
 for(let i=0;i<meshes.length;i++){const instance=new THREE.Matrix4();batch.getMatrixAt(i,instance);assert.ok(instance.determinant()>0);const actual=batch.matrixWorld.clone().multiply(instance);for(let k=0;k<16;k++)assert.ok(Math.abs(actual.elements[k]-before[i].elements[k])<1e-6);const originalNormal=new THREE.Matrix3().getNormalMatrix(before[i]),normal=new THREE.Matrix3().getNormalMatrix(actual);for(let k=0;k<9;k++)assert.ok(Math.abs(normal.elements[k]-originalNormal.elements[k])<1e-6);}
 meshes[1].visible=false;batching.sync();assert.equal(batch.count,2);batching.sync(false);assert.ok(meshes.every(m=>m.layers.mask===1));
});

test('Float32 orthogonality roundoff batches within normal tolerance while positions stay unchanged',async()=>{
 const THREE=await import('../../../devtools/web/node_modules/three/build/three.module.js');
 const {batchStaticMeshes}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
 const scene=new THREE.Scene(),geometry=new THREE.BoxGeometry(),material=new THREE.MeshStandardMaterial();
 const meshes=Array.from({length:2},(_,i)=>{const mesh=new THREE.Mesh(geometry,material);mesh.matrixAutoUpdate=false;mesh.matrix.elements[4]=3e-7;mesh.matrix.elements[12]=i*2;mesh.userData={module:'M01',floor:1};scene.add(mesh);return mesh;});scene.updateMatrixWorld(true);
 const batching=batchStaticMeshes(meshes,scene);batching.sync();assert.equal(batching.batches.length,1);const batch=batching.batches[0],matrix=new THREE.Matrix4();batch.getMatrixAt(0,matrix);
 const im=new THREE.Matrix3().setFromMatrix4(matrix),scale=new THREE.Vector3(...[0,1,2].map(i=>new THREE.Vector3().setFromMatrixColumn(matrix,i).lengthSq()));
 for(const input of [new THREE.Vector3(1,0,0),new THREE.Vector3(0,1,0),new THREE.Vector3(1,2,3)]){const actual=input.clone().divide(scale).applyMatrix3(im).applyMatrix3(new THREE.Matrix3().getNormalMatrix(batch.matrixWorld)).normalize(),expected=input.clone().applyMatrix3(new THREE.Matrix3().getNormalMatrix(meshes[0].matrixWorld)).normalize();assert.ok(actual.distanceTo(expected)<1e-6);}
 const world=batch.matrixWorld.clone().multiply(matrix);for(let i=0;i<16;i++)assert.ok(Math.abs(world.elements[i]-meshes[0].matrixWorld.elements[i])<1e-12);
});
