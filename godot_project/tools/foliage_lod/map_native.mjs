// Reproducible build-only glTF -> current Godot import mapping. Never mutates .godot or formal sources.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname),'../../..');
const out=path.resolve(process.argv[2] || 'build/godot_assets/foliage-lod-regenerated');
assert(out.startsWith(path.join(root,'build')+path.sep));
process.chdir(root);
const base=JSON.parse(fs.readFileSync(path.join(out,'baseline.json'))),candidates=JSON.parse(fs.readFileSync(path.join(out,'candidate-lods.json')));
const candidate=candidates.levels.find(x=>x.target_triangles===2000);
assert(candidate?.geometry_verified && candidate.triangles===2000);
const sha=x=>crypto.createHash('sha256').update(x).digest('hex'),source=fs.readFileSync(base.source_path),cache=fs.readFileSync(base.imported_cache_path);
assert.equal(sha(source),base.source_sha256);assert.equal(sha(cache),base.imported_cache_sha256);
const n=source.readUInt32LE(12),doc=JSON.parse(source.subarray(20,20+n)),bin=source.subarray(28+n),prim=doc.meshes[0].primitives[0];
function read(i){
 const a=doc.accessors[i],v=doc.bufferViews[a.bufferView],sz={5121:1,5123:2,5125:4,5126:4}[a.componentType],nc={SCALAR:1,VEC3:3,VEC4:4}[a.type],result=[];
 assert(!a.sparse&&!v.extensions);
 for(let j=0;j<a.count;j++){let row=[];for(let k=0;k<nc;k++){
  const at=(v.byteOffset||0)+(a.byteOffset||0)+j*(v.byteStride||sz*nc)+k*sz;
  row.push(a.componentType===5126?bin.readFloatLE(at):a.componentType===5123?bin.readUInt16LE(at):a.componentType===5125?bin.readUInt32LE(at):bin[at]);
 }result.push(row);}return result;
}
const positions=read(prim.attributes.POSITION),normals=read(prim.attributes.NORMAL),tangents=read(prim.attributes.TANGENT),colors=read(prim.attributes.COLOR_0),indices=read(prim.indices).flat();
assert.equal(doc.accessors[prim.attributes.COLOR_0].componentType,5121);assert(doc.accessors[prim.attributes.COLOR_0].normalized);
const s=base.surface,vd=Buffer.from(s.vertex_data[1],'hex'),ad=Buffer.from(s.attribute_data[1],'hex'),ib=Buffer.from(s.index_data[1],'hex');
assert.equal(s.vertex_count,positions.length);assert.equal(vd.length,s.vertex_count*20);assert.equal(ad.length,s.vertex_count*4);
function oct(x,y){x=x*2-1;y=y*2-1;const z=1-Math.abs(x)-Math.abs(y),t=Math.max(0,Math.min(1,-z));x+=x>=0?-t:t;y+=y>=0?-t:t;const l=Math.hypot(x,y,z);return[x/l,y/l,z/l];}
const groups=new Map();positions.forEach((p,i)=>{const k=p.join(',');if(!groups.has(k))groups.set(k,[]);groups.get(k).push(i);});
const nativeToSource=[],sourceToNative=new Array(positions.length).fill(-1);
let maxNormalDelta=0,maxTangentDelta=0,minAlternativeSeparation=Infinity;
for(let i=0;i<s.vertex_count;i++){
 const p=[0,1,2].map(k=>vd.readFloatLE(i*12+k*4)),at=s.vertex_count*12+i*8;
 const normal=oct(vd.readUInt16LE(at)/65535,vd.readUInt16LE(at+2)/65535),ty=vd.readUInt16LE(at+6)/65535*2-1,tangent=oct(vd.readUInt16LE(at+4)/65535,Math.abs(ty)),sign=Math.sign(ty),color=Array.from(ad.subarray(i*4,i*4+4));
 const possible=(groups.get(p.join(','))||[]).map(j=>({j,nd:Math.hypot(...normal.map((x,k)=>x-normals[j][k])),td:Math.hypot(...tangent.map((x,k)=>x-tangents[j][k])),color:color.every((x,k)=>x===colors[j][k]),sign:sign===tangents[j][3]}));
 // Tolerances cover existing oct16 decoding only. No attributes are re-encoded.
 const accepted=possible.filter(x=>x.nd<=.0002 && x.td<=.0003 && x.color && x.sign);
 assert.equal(accepted.length,1,'All native corners must have an unambiguous full-attribute match: '+i);
 const {j,nd,td}=accepted[0];assert.equal(sourceToNative[j],-1,'Mapping must be bijective');
 nativeToSource[i]=j;sourceToNative[j]=i;maxNormalDelta=Math.max(maxNormalDelta,nd);maxTangentDelta=Math.max(maxTangentDelta,td);
 for(const alternative of possible)if(alternative.j!==j)minAlternativeSeparation=Math.min(minAlternativeSeparation,Math.hypot(alternative.nd,alternative.td));
}
assert(sourceToNative.every(i=>i>=0));
function orientedKey(a,b,c){return [[a,b,c],[b,c,a],[c,a,b]].map(x=>x.join('|')).sort()[0];}
function multiset(ix,flip=false,label=x=>x){
 const m=new Map();for(let i=0;i<ix.length;i+=3){const a=label(ix[i]),b=label(ix[i+(flip?2:1)]),c=label(ix[i+(flip?1:2)]),k=orientedKey(a,b,c);m.set(k,(m.get(k)||0)+1);}return m;
}
function equal(a,b){return a.size===b.size&&[...a].every(([k,v])=>b.get(k)===v);}
const nativeIndices=Array.from({length:ib.length/2},(_,i)=>ib.readUInt16LE(i*2));
const nativeSource=nativeIndices.map(i=>nativeToSource[i]),originalFaces=multiset(indices);
const same=equal(originalFaces,multiset(nativeSource)),reverse=equal(originalFaces,multiset(nativeSource,true));
assert(same!==reverse,'Full oriented base triangle multiset must identify winding uniquely');
const sh=base.shadow_surface,sv=Buffer.from(sh.vertex_data[1],'hex'),si=Buffer.from(sh.index_data[1],'hex');
const shadowPositions=Array.from({length:sh.vertex_count},(_,i)=>[0,1,2].map(k=>sv.readFloatLE(i*12+k*4)));
const shadowByPosition=new Map(shadowPositions.map((p,i)=>[p.join(','),i]));assert.equal(shadowByPosition.size,sh.vertex_count);
const sourceToShadow=positions.map(p=>{const i=shadowByPosition.get(p.join(','));assert.notEqual(i,undefined);return i;});
const shadowIndices=Array.from({length:si.length/2},(_,i)=>si.readUInt16LE(i*2));
assert(equal(multiset(indices,false,i=>positions[i].join(',')),multiset(shadowIndices,reverse,i=>shadowPositions[i].join(','))),'Shadow base oriented position triangles must match original');
function convert(ix,map){
 const result=Buffer.alloc(ix.length*2);
 for(let i=0;i<ix.length;i++){const j=reverse?i-i%3+(i%3===0?0:3-i%3):i;result.writeUInt16LE(map[ix[j]],i*2);}return result;
}
const main=convert(candidate.indices,sourceToNative),shadow=convert(candidate.indices,sourceToShadow);
const outputIndices=Array.from({length:main.length/2},(_,i)=>main.readUInt16LE(i*2));
assert(equal(multiset(candidate.indices),multiset(outputIndices,reverse,i=>nativeToSource[i])));
const outputShadow=Array.from({length:shadow.length/2},(_,i)=>shadow.readUInt16LE(i*2));
assert(equal(multiset(candidate.indices,false,i=>positions[i].join(',')),multiset(outputShadow,reverse,i=>shadowPositions[i].join(','))));
// Conservative for the current formal buffers even when renderer ignores instance scale.
// Serialize exactly representable float32, rounded upward (never understate error).
const rawEdge=candidate.world_error_upper_m*1.000001;
const edgeBytes=Buffer.alloc(4);edgeBytes.writeFloatLE(rawEdge);
if(edgeBytes.readFloatLE()<rawEdge)edgeBytes.writeUInt32LE(edgeBytes.readUInt32LE()+1);
const edge=edgeBytes.readFloatLE();
function patch(surface,data){
 const copy=structuredClone(surface),old=copy.lods;
 assert(edge<old[0]);copy.lods=[edge,['bytes',data.toString('hex')],...old];
 assert.deepEqual({...copy,lods:copy.lods.slice(2)},surface);
 return copy;
}
const patched=patch(s,main),patchedShadow=patch(sh,shadow);
fs.writeFileSync(path.join(out,'lod-2000.native-indices.u16'),main);
fs.writeFileSync(path.join(out,'lod-2000.native-shadow-indices.u16'),shadow);
const report={
 status:'NATIVE_MAPPING_VERIFIED_BUILD_ONLY_ENGINE_AND_VISUAL_VALIDATION_PENDING',
 source_sha256:base.source_sha256,imported_cache_sha256:base.imported_cache_sha256,
 mapping:{source_vertices:positions.length,native_vertices:s.vertex_count,bijection:true,positions_exact:true,colors_exact:true,tangent_handedness_exact:true,normal_oct16_max_vector_delta:maxNormalDelta,tangent_oct16_max_vector_delta:maxTangentDelta,normal_decode_tolerance:.0002,tangent_decode_tolerance:.0003,min_wrong_candidate_normal_tangent_separation:minAlternativeSeparation,oriented_base_triangles_equal:true,reverse_winding:reverse,shadow_vertices:sh.vertex_count,shadow_base_position_triangles_equal:true,candidate_main_and_shadow_triangles_equal:true},
 candidate:{triangles:2000,prototype_error_upper_m:candidate.prototype_error_upper_m,world_error_upper_m:candidate.world_error_upper_m,conservative_lod_edge:edge,default_1px_switch_distance_m:edge*1212/(2*Math.tan(19*Math.PI/180)*(1212/900)),main_indices_sha256:sha(main),shadow_indices_sha256:sha(shadow)},
 preservation:{base_surface_all_fields_except_lods_exact:true,shadow_surface_all_fields_except_lods_exact:true,existing_lod_entries_exact:true,base_and_shadow_vertex_attributes_exact:true,source_material_reference_exact:true,near_base_index_buffers_exact:true,rollback_remove_first_lod_pair_exact:true,formal_files_unchanged:true},
 main_lod_table:patched.lods.map((v,i)=>i%2===0?{edge:v,indices:patched.lods[i+1][1].length/4}:null).filter(Boolean),
 shadow_lod_table:patchedShadow.lods.map((v,i)=>i%2===0?{edge:v,indices:patchedShadow.lods[i+1][1].length/4}:null).filter(Boolean)
};
const payload={...report,source_to_native:sourceToNative,source_to_shadow:sourceToShadow,append_native_index_hex:main.toString('hex'),append_shadow_index_hex:shadow.toString('hex')};
fs.writeFileSync(path.join(out,'native-patch.json'),JSON.stringify(payload,null,2)+'\n');
fs.writeFileSync(path.join(out,'native-mapping-report.json'),JSON.stringify(report,null,2)+'\n');
assert.equal(sha(fs.readFileSync(base.source_path)),base.source_sha256);assert.equal(sha(fs.readFileSync(base.imported_cache_path)),base.imported_cache_sha256);
function fingerprint(surface){
 const fields={};
 for(const [key,value]of Object.entries(surface)){
  if(key==='material')continue; // Kept by identity, never reconstructed.
  if(key==='lods')fields[key]=value.map((v,i)=>i%2?{sha256:sha(Buffer.from(v[1],'hex')),bytes:v[1].length/2}:v);
  else if(Array.isArray(value)&&value[0]==='bytes')fields[key]={sha256:sha(Buffer.from(value[1],'hex')),bytes:value[1].length/2};
  else fields[key]=value;
 }
 return {keys:Object.keys(surface).sort(),fields};
}
const sidecar={
 source_path:'res://'+base.source_path.replace(/^godot_project\//,''),source_sha256:base.source_sha256,
 node:'part_00006',mesh_name:base.mesh_name,triangles:2000,lod_edge:edge,
 prototype_error_upper_m:candidate.prototype_error_upper_m,world_stretch_upper:base.world_stretch_upper,
 scene_sha256:Object.fromEntries(Object.entries(base.scene_sha256).map(([k,v])=>['res://'+k.replace(/^godot_project\//,''),v])),
 main:{baseline:fingerprint(s),indices_hex:main.toString('hex'),indices_sha256:sha(main)},
 shadow:{baseline:fingerprint(sh),indices_hex:shadow.toString('hex'),indices_sha256:sha(shadow)},
 generator:'godot_project/tools/foliage_lod/README.md'
};
const sidecarText=JSON.stringify(sidecar,null,2)+'\n';
fs.writeFileSync(path.join(out,'forest-foliage.lods.json'),sidecarText);
if(process.argv.includes('--write-sidecar'))fs.writeFileSync(base.source_path.replace(/\.glb$/,'.lods.json'),sidecarText);
console.log(JSON.stringify({status:report.status,candidate:report.candidate,sidecar:path.join(out,'forest-foliage.lods.json'),formal_written:process.argv.includes('--write-sidecar')},null,2));
