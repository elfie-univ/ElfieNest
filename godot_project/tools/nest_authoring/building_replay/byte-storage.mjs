import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import path from 'node:path';
import { task as root } from './geometry.mjs';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const align=n=>(n+3)&~3;
function read(raw){
  const n=raw.readUInt32LE(12), start=28+n;
  assert.deepEqual([raw.readUInt32LE(0),raw.readUInt32LE(4),raw.readUInt32LE(8),raw.readUInt32LE(16),raw.readUInt32LE(start-8),raw.readUInt32LE(start-4)],[0x46546c67,2,raw.length,0x4e4f534a,raw.length-start,0x004e4942]);
  return [JSON.parse(raw.subarray(20,20+n)),raw.subarray(start)];
}
function payload(d,b,i){
  const v=d.bufferViews[i];
  assert(v.buffer===0 && v.byteOffset%4===0 && v.byteOffset+v.byteLength<=b.length && !v.byteStride && !v.extensions);
  return b.subarray(v.byteOffset,v.byteOffset+v.byteLength);
}
function write(doc,b){
  const json=Buffer.from(JSON.stringify(doc)), n=align(json.length), out=Buffer.alloc(28+n+b.length);
  for(const [i,v] of [0x46546c67,2,out.length,n,0x4e4f534a].entries())out.writeUInt32LE(v,i*4);
  out.fill(32,20,20+n);json.copy(out,20);
  out.writeUInt32LE(b.length,20+n);out.writeUInt32LE(0x004e4942,24+n);b.copy(out,28+n);
  return out;
}
function decodedIndex(a,b,j){return a.componentType===5125?b.readUInt32LE(j*4):a.componentType===5123?b.readUInt16LE(j*2):b.readUInt8(j);}
function run(file, expected){
  const src=path.join(root,'before',file), dst=path.join(root,'candidates',file), raw=fs.readFileSync(src);
  assert.equal(sha(raw),expected);
  const [doc,bin]=read(raw), next=structuredClone(doc);
  assert(!doc.animations&&!doc.skins&&doc.buffers.length===1&&!doc.buffers[0].uri);
  const prim=doc.meshes.flatMap(m=>m.primitives);
  assert(prim.every(p=>(p.mode??4)===4&&!p.targets&&!p.extensions));
  const colors=new Set(prim.map(p=>p.attributes.COLOR_0).filter(i=>i!==undefined)), indices=new Set(prim.map(p=>p.indices));
  const payloads=doc.bufferViews.map((_,i)=>payload(doc,bin,i)), changed=new Map();
  const exclusive=i=>doc.accessors.filter(a=>a.bufferView===doc.accessors[i].bufferView).length===1;
  let colorVertices=0, byteIndexAccessors=0;
  for(const i of colors){
    const a=doc.accessors[i], b=payloads[a.bufferView];
    assert(a.componentType===5126&&a.type==='VEC3'&&!a.normalized&&!a.byteOffset&&!a.sparse&&exclusive(i));
    assert.equal(b.length,a.count*12);
    const c=Buffer.alloc(a.count*4,255);
    for(let j=0;j<a.count;j++)for(let k=0;k<3;k++){
      const x=b.readFloatLE(j*12+k*4), u=Math.round(x*255);
      assert(u>=0&&u<=255&&Object.is(Math.fround(u/255),x));c[j*4+k]=u;
    }
    payloads[a.bufferView]=c;changed.set(i,'color');colorVertices+=a.count;
    Object.assign(next.accessors[i],{type:'VEC4',componentType:5121,normalized:true});
    for(const field of ['min','max'])if(a[field])next.accessors[i][field]=[...a[field].map(x=>Math.round(x*255)),255];
  }
  for(const i of indices){
    const a=doc.accessors[i], b=payloads[a.bufferView];
    assert(a.type==='SCALAR'&&!a.byteOffset&&!a.sparse&&!a.normalized&&[5123,5125].includes(a.componentType));
    if(a.componentType!==5123||!exclusive(i))continue;
    let max=0;
    for(let j=0;j<a.count;j++)max=Math.max(max,decodedIndex(a,b,j));
    if(max>=255)continue;
    const c=Buffer.alloc(a.count);
    for(let j=0;j<a.count;j++)c[j]=decodedIndex(a,b,j);
    payloads[a.bufferView]=c;changed.set(i,'index');next.accessors[i].componentType=5121;byteIndexAccessors++;
  }
  let size=0;
  for(const [i,b] of payloads.entries()){
    Object.assign(next.bufferViews[i],{byteOffset:size,byteLength:b.length});size+=align(b.length);
  }
  next.buffers[0].byteLength=size;
  const outBin=Buffer.alloc(size);
  for(const [i,b] of payloads.entries())b.copy(outBin,next.bufferViews[i].byteOffset);
  const out=write(next,outBin), [test,testBin]=read(out);
  for(const k of Object.keys(doc).filter(k=>!['accessors','buffers','bufferViews'].includes(k)))assert.deepEqual(test[k],doc[k],k);
  for(const [i,a] of doc.accessors.entries()){
    const t=test.accessors[i], aBytes=payload(doc,bin,a.bufferView), tBytes=payload(test,testBin,t.bufferView);
    if(changed.get(i)==='index'){
      for(let j=0;j<a.count;j++)assert.equal(decodedIndex(t,tBytes,j),decodedIndex(a,aBytes,j));
    }else if(changed.get(i)==='color'){
      for(let j=0;j<a.count;j++){
        for(let k=0;k<3;k++)assert(Object.is(Math.fround(tBytes[j*4+k]/255),aBytes.readFloatLE(j*12+k*4)));
        assert.equal(tBytes[j*4+3],255);
      }
    }else{
      assert.deepEqual(t,a);assert(aBytes.equals(tBytes),i);
    }
  }
  for(const p of prim){
    const a=test.accessors[p.indices], ib=payload(test,testBin,a.bufferView), count=test.accessors[p.attributes.POSITION].count;
    assert.equal(a.count%3,0);
    for(let j=0;j<a.count;j++)assert(decodedIndex(a,ib,j)<count);
  }
  for(const i of doc.images??[])assert(i.uri&&!i.bufferView&&sha(fs.readFileSync(path.resolve(path.dirname(src),i.uri)))===sha(fs.readFileSync(path.resolve(path.dirname(dst),i.uri))));
  assert(out.length<raw.length);
  fs.writeFileSync(dst,out,{flag:'wx'});
  return {file,before:raw.length,after:out.length,saved:raw.length-out.length,beforeSha256:sha(raw),afterSha256:sha(out),byteIndexAccessors,colorVertices,triangles:prim.reduce((n,p)=>n+doc.accessors[p.indices].count/3,0),meshResources:doc.meshes.length,materials:doc.materials.length,exactDecodedAttributesAndIndices:true,unchangedSceneAndTextures:true};
}
const report=[
  run('main/central-building.glb','15948daf7482d500591c4d1f766ff7a1ccb95e3b4294b368adff8f5a2bc6f8b8'),
  run('pod/pod-building.glb','2bdaf46cee2d0cb9e296c4a7ac5c7eea57d79fdaf07b9598f272393f3a1f040f')
];
fs.writeFileSync(path.join(root,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(report);
