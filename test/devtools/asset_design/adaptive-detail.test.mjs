import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
const root=new URL('../../../',import.meta.url);
const THREE=await import(new URL('devtools/web/node_modules/three/build/three.module.js',root));
let source=await readFile(new URL('devtools/asset_design/web/adaptive-detail.mjs',root),'utf8');
source=source.replace("'/assets/design/library/three.module.js'",JSON.stringify(new URL('devtools/web/node_modules/three/build/three.module.js',root).href));
const {createAdaptiveDetail,detailJob,simplifyDetail,prepareAdaptiveDetail}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const {MeshoptSimplifier:S}=await import(new URL('devtools/web/node_modules/three/examples/jsm/libs/meshopt_simplifier.module.js',root));
await S.ready;
test('far detail keeps attributes and locked opening edges; near and shadow frames restore exact indices',()=>{
 const g=new THREE.SphereGeometry(1,128,64),mesh=new THREE.Mesh(g,new THREE.MeshStandardMaterial());mesh.updateMatrixWorld(true);
 const original=g.index,attributes={...g.attributes},job=detailJob(g),result=simplifyDetail(job,S);
 assert.ok(result.indices.length<original.count*.9);assert.ok(result.error<=.0005);
 const detail=createAdaptiveDetail([mesh]);detail.accept(g,result);
 const camera=new THREE.PerspectiveCamera(42,1,.01,200);camera.position.z=100;detail.update(camera,800);
 assert.notStrictEqual(g.index,original);assert.deepEqual(g.attributes,attributes);
 camera.position.z=1.01;detail.update(camera,800);assert.strictEqual(g.index,original);
 camera.position.z=100;detail.update(camera,800,{fullDetail:true});assert.strictEqual(g.index,original);
 detail.update(camera,800);assert.notStrictEqual(g.index,original);detail.dispose();assert.strictEqual(g.index,original);
});
test('any close instance keeps shared geometry precise, and glass, lights and moving meshes are excluded',()=>{
 const g=new THREE.SphereGeometry(1,128,64),a=new THREE.Mesh(g,new THREE.MeshStandardMaterial()),b=a.clone();b.position.z=99;const scene=new THREE.Scene();scene.add(a,b);scene.updateMatrixWorld(true);
 const original=g.index,detail=createAdaptiveDetail([a,b]);detail.accept(g,{indices:original.array.slice(0,300),error:.0005});
 const camera=new THREE.PerspectiveCamera(42,1,.01,200);camera.position.z=100;detail.update(camera,800);assert.strictEqual(g.index,original);
 for(const edit of [m=>m.userData.glass=true,m=>m.material.emissive.set(0xffffff),m=>m.isSkinnedMesh=true,m=>m.geometry.morphAttributes.position=[m.geometry.attributes.position]]){
  const m=new THREE.Mesh(new THREE.SphereGeometry(1,128,64),new THREE.MeshStandardMaterial());edit(m);assert.equal(createAdaptiveDetail([m]).jobs().length,0);
 }
});
test('texture preview reduction is distance dependent, retains samplers and restores original source',()=>{
 const texture=new THREE.Texture({width:2048,height:2048}),source=texture.source;texture.offset.set(.2,.3);texture.repeat.set(1.3,1.2);texture.colorSpace=THREE.SRGBColorSpace;
 const mesh=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:texture}));mesh.updateMatrixWorld(true);
 const detail=createAdaptiveDetail([mesh],{makeImage:(image,w,h)=>({width:w,height:h})}),camera=new THREE.PerspectiveCamera(42,1,.01,200);camera.position.z=100;detail.update(camera,800);
 assert.notStrictEqual(texture.source,source);assert.equal(texture.source.data.width,1024);assert.deepEqual(texture.offset.toArray(),[.2,.3]);assert.deepEqual(texture.repeat.toArray(),[1.3,1.2]);assert.equal(texture.colorSpace,THREE.SRGBColorSpace);
 assert.ok(detail.stats().textureBytesSaved>0);camera.position.z=.4;detail.update(camera,800);assert.strictEqual(texture.source,source);assert.equal(detail.stats().textureBytesSaved,0);
 detail.dispose();assert.strictEqual(texture.source,source);
});
test('closed preview rejects late worker results without mutating or retaining geometry',()=>{
 const g=new THREE.SphereGeometry(1,128,64),m=new THREE.Mesh(g,new THREE.MeshStandardMaterial()),original=g.index,detail=createAdaptiveDetail([m]);detail.dispose();detail.accept(g,{indices:original.array.slice(0,300),error:.0005});assert.strictEqual(g.index,original);assert.equal(detail.stats().geometries,0);
});

test('worker numeric surface error is accepted; geometry preparation completes and worker is terminated',async()=>{
 const Original=globalThis.Worker;let stopped=0;
 globalThis.Worker=class {postMessage(data){queueMicrotask(()=>this.onmessage({data:data.url?{ready:true}:{indices:new Uint32Array([0,1,2]),error:.0004}}));}terminate(){stopped++;}};
 const g=new THREE.SphereGeometry(1,128,64),mesh=new THREE.Mesh(g,new THREE.MeshStandardMaterial()),detail=createAdaptiveDetail([mesh]);
 try{await prepareAdaptiveDetail(detail,{workerURL:'https://assets.test/simplifier'});assert.equal(detail.stats().geometries,1);assert.equal(stopped,1);}finally{globalThis.Worker=Original;detail.dispose();}
});

test('only small distant transmission uses a smaller offscreen buffer; close glass and full detail retain full size',()=>{
 const mesh=new THREE.Mesh(new THREE.SphereGeometry(),new THREE.MeshPhysicalMaterial({transmission:.82}));mesh.updateMatrixWorld(true);
 const detail=createAdaptiveDetail([mesh]),camera=new THREE.PerspectiveCamera(42,1,.01,200);camera.position.z=100;
 detail.update(camera,800);assert.equal(detail.transmissionScale(),.5);
 camera.position.z=3;detail.update(camera,800);assert.equal(detail.transmissionScale(),1);
 camera.position.z=100;detail.update(camera,800,{fullDetail:true});assert.equal(detail.transmissionScale(),1);
});

test('shared glass geometry and color images used by emissive maps cannot be reduced indirectly',()=>{
 const geometry=new THREE.SphereGeometry(1,128,64),a=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial()),b=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial());b.userData.glass=true;
 assert.equal(createAdaptiveDetail([a,b]).jobs().length,0);
 const texture=new THREE.Texture({width:2048,height:2048}),original=texture.source;
 const material=new THREE.MeshStandardMaterial({map:texture,emissiveMap:texture});const mesh=new THREE.Mesh(new THREE.BoxGeometry(),material);mesh.updateMatrixWorld(true);
 const detail=createAdaptiveDetail([mesh],{makeImage:()=>{throw Error('Protected light map must not be resampled');}}),camera=new THREE.PerspectiveCamera();camera.position.z=100;detail.update(camera,800);assert.strictEqual(texture.source,original);
});
