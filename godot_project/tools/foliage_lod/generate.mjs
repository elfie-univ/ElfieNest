// Regenerate only the accepted 2000-triangle candidate into build/. Never invokes Godot.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { MeshoptSimplifier as S } from '../../../devtools/web/node_modules/three/examples/jsm/libs/meshopt_simplifier.module.js';
import { Vector3, Triangle } from '../../../devtools/web/node_modules/three/build/three.module.js';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../..');
const out = path.resolve(process.argv[2] || 'build/godot_assets/foliage-lod-regenerated');
assert(out.startsWith(path.join(root, 'build') + path.sep));
process.chdir(root);
const baseline = JSON.parse(fs.readFileSync(path.join(out,'baseline.json')));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const raw = fs.readFileSync(baseline.source_path);
assert.equal(sha(raw), baseline.source_sha256);
assert.equal(sha(fs.readFileSync(baseline.imported_cache_path)), baseline.imported_cache_sha256);
assert.equal(baseline.source_sha256, '6be42ff95a5cdd62e71c94b35584241c7bfd90927a721708ba65150ad7a71ef1', 'Changed source requires a new quality review');
const n = raw.readUInt32LE(12), doc = JSON.parse(raw.subarray(20,20+n)), bin = raw.subarray(28+n);
const primitive = doc.meshes[0].primitives[0];
assert.equal(doc.meshes[0].primitives.length,1);
assert(!primitive.targets && !primitive.extensions && !doc.skins?.length && !doc.animations?.length);
function accessor(i) {
 const a=doc.accessors[i],v=doc.bufferViews[a.bufferView];
 assert(!a.sparse && !v.extensions);
 const bytes={5121:1,5123:2,5125:4,5126:4}[a.componentType],nc={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type];
 assert(bytes && nc);
 const result=[];
 for(let j=0;j<a.count;j++)for(let k=0;k<nc;k++) {
  const at=(v.byteOffset||0)+(a.byteOffset||0)+j*(v.byteStride||bytes*nc)+k*bytes;
  let value=a.componentType===5126?bin.readFloatLE(at):a.componentType===5123?bin.readUInt16LE(at):a.componentType===5125?bin.readUInt32LE(at):bin[at];
  if(a.normalized)value/=a.componentType===5121?255:a.componentType===5123?65535:4294967295;
  result.push(value);
 }
 return result;
}
const positions=new Float32Array(accessor(primitive.attributes.POSITION));
const original=new Uint32Array(accessor(primitive.indices));
const vertexCount=positions.length/3;
const points=Array.from({length:vertexCount},(_,i)=>new Vector3(...positions.slice(i*3,i*3+3)));
const semantics=['NORMAL','TANGENT','COLOR_0'];
assert.deepEqual(Object.keys(primitive.attributes).sort(),['COLOR_0','NORMAL','POSITION','TANGENT']);
const attributes=Object.fromEntries(semantics.map(k=>[k,accessor(primitive.attributes[k])]));
const flat=[];
for(let i=0;i<vertexCount;i++)for(const k of semantics)flat.push(...attributes[k].slice(i*(k==='NORMAL'?3:4),(i+1)*(k==='NORMAL'?3:4)));
const attributeBuffer=new Float32Array(flat);
const parent=Array.from({length:vertexCount},(_,i)=>i);
function find(i){while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;}
for(let i=0;i<original.length;i+=3)for(let k=1;k<3;k++)parent[find(original[i+k])]=find(original[i]);
const component=parent.map((_,i)=>find(i));
const kept=[], removed=[];
for(let i=0;i<original.length;i+=3) {
 const ids=Array.from(original.slice(i,i+3)),t=new Triangle(...ids.map(i=>points[i]));
 if(t.getArea()===0)removed.push(i/3);else kept.push(...ids);
}
assert.equal(removed.length,192);
const clean=new Uint32Array(kept);
const locks=new Uint8Array(vertexCount);
const positionGroups=new Map();
for(let i=0;i<vertexCount;i++){const k=points[i].toArray().join(',');if(!positionGroups.has(k))positionGroups.set(k,[]);positionGroups.get(k).push(i);}
for(const ids of positionGroups.values()) {
 const signatures=new Set(ids.map(i=>attributeBuffer.slice(i*11,i*11+11).join(',')));
 if(signatures.size>1)for(const i of ids)locks[i]=1;
}
// Protect each disconnected leaf's six AABB extrema as well as attribute seams.
for(const c of new Set(component)) {
 const ids=component.map((v,i)=>v===c?i:-1).filter(i=>i>=0);
 for(const axis of ['x','y','z'])for(const fn of [Math.min,Math.max]) {
  const extreme=fn(...ids.map(i=>points[i][axis]));
  for(const i of ids)if(points[i][axis]===extreme)locks[i]=1;
 }
}
// The importer reorders vertices. These files intentionally remain in the
// original glTF accessor index space; no native ArrayMesh mutation is emitted.
function sourcePack(indices) {
 const result=Buffer.alloc(indices.length*2);
 for(let i=0;i<indices.length;i++)result.writeUInt16LE(indices[i],i*2);
 return result;
}
function faces(indices) {
 const groups=new Map();
 for(let i=0;i<indices.length;i+=3) {
  const ids=Array.from(indices.slice(i,i+3)),c=component[ids[0]];
  assert(ids.every(id=>Number.isInteger(id)&&id>=0&&id<vertexCount&&component[id]===c));
  const tri=new Triangle(...ids.map(id=>points[id]));
  assert(tri.getArea()>0,'No new degenerate faces');
  if(!groups.has(c))groups.set(c,[]);
  groups.get(c).push({ids,tri,key:[ids,[ids[1],ids[2],ids[0]],[ids[2],ids[0],ids[1]]].map(t=>t.join(',')).sort()[0]});
 }
 assert.equal(groups.size,24,'No component may disappear');
 return groups;
}
const baseFaces=faces(clean);
const tmp=new Vector3();
function nearest(p,triangles) {
 let best=null,dist=Infinity,closest=null;
 for(const f of triangles){f.tri.closestPointToPoint(p,tmp);const d=tmp.distanceToSquared(p);if(d<dist){dist=d;best=f;closest=tmp.clone();}}
 return {face:best,point:closest,distance:Math.sqrt(dist)};
}
function interpolate(f,p,k) {
 const bary=f.tri.getBarycoord(p,new Vector3()),w=[bary.x,bary.y,bary.z],size=k==='NORMAL'?3:4;
 return Array.from({length:size},(_,j)=>f.ids.reduce((sum,id,i)=>sum+attributes[k][id*size+j]*w[i],0));
}
function angle(a,b) {
 const al=Math.hypot(...a),bl=Math.hypot(...b);
 if(al<1e-12||bl<1e-12)return 180;
 return Math.acos(Math.max(-1,Math.min(1,a.reduce((s,x,i)=>s+x*b[i],0)/(al*bl))))*180/Math.PI;
}
// Each accepted patch maps its three corners onto ONE target triangle.
// Convex interpolation gives a correspondence for every interior point;
// max corner separation bounds the ENTIRE patch, not just sampled points.
// Four-way subdivision tightens this bound near target triangle boundaries.
function directed(source,target,cap) {
 const report={upper_m:0,sampled_lower_m:0,patches:0,max_depth:0,normal_angle_sample_deg:0,tangent_angle_sample_deg:0,color_channel_sample_max:0,handedness_mismatches:0,opposed_nearest_face_samples:0};
 function sample(f,p,near) {
  report.sampled_lower_m=Math.max(report.sampled_lower_m,near.distance);
  const a=interpolate(f,p,'NORMAL'),b=interpolate(near.face,near.point,'NORMAL');
  report.normal_angle_sample_deg=Math.max(report.normal_angle_sample_deg,angle(a,b));
  const ta=interpolate(f,p,'TANGENT'),tb=interpolate(near.face,near.point,'TANGENT');
  report.tangent_angle_sample_deg=Math.max(report.tangent_angle_sample_deg,angle(ta.slice(0,3),tb.slice(0,3)));
  if(Math.sign(ta[3])!==Math.sign(tb[3]))report.handedness_mismatches++;
  const ca=interpolate(f,p,'COLOR_0'),cb=interpolate(near.face,near.point,'COLOR_0');
  report.color_channel_sample_max=Math.max(report.color_channel_sample_max,...ca.map((v,i)=>Math.abs(v-cb[i])));
  if(f.tri.getNormal(new Vector3()).dot(near.face.tri.getNormal(new Vector3()))<0)report.opposed_nearest_face_samples++;
 }
 function visit(f,a,b,c,targets,depth) {
  report.patches++;report.max_depth=Math.max(report.max_depth,depth);
  const center=a.clone().add(b).add(c).multiplyScalar(1/3),near=nearest(center,targets);
  sample(f,center,near);
  let upper=0;
  for(const p of [a,b,c]){
   const q=near.face.tri.closestPointToPoint(p,new Vector3());
   upper=Math.max(upper,p.distanceTo(q));
   sample(f,p,nearest(p,targets));
  }
  upper+=1e-7; // absolute floating-point allowance in prototype metres
  if(upper<=cap){report.upper_m=Math.max(report.upper_m,upper);return;}
  if(report.sampled_lower_m>cap||depth===12)throw Error('Surface bound failed '+JSON.stringify({cap,upper,lower:report.sampled_lower_m,depth}));
  const ab=a.clone().add(b).multiplyScalar(.5),bc=b.clone().add(c).multiplyScalar(.5),ca=c.clone().add(a).multiplyScalar(.5);
  visit(f,a,ab,ca,targets,depth+1);visit(f,ab,b,bc,targets,depth+1);visit(f,ca,bc,c,targets,depth+1);visit(f,ab,bc,ca,targets,depth+1);
 }
 for(const [c,fsrc] of source){
  const targets=target.get(c),keys=new Set(targets.map(f=>f.key));
  for(const f of fsrc){if(keys.has(f.key))continue;visit(f,f.tri.a,f.tri.b,f.tri.c,targets,0);}
 }
 return report;
}
// Focused verifier checks: identity, known displacement, reversed orientation.
assert.equal(directed(baseFaces,baseFaces,.01).upper_m,0);
const testFace=baseFaces.values().next().value[0];
const shifted={...testFace,key:'shifted',tri:new Triangle(...[testFace.tri.a,testFace.tri.b,testFace.tri.c].map(p=>p.clone().addScalar(1)))};
assert.throws(()=>directed(new Map([[0,[testFace]]]),new Map([[0,[shifted]]]),.03),/Surface bound failed/);
const reversed={...testFace,key:'reversed',ids:[testFace.ids[0],testFace.ids[2],testFace.ids[1]],tri:new Triangle(testFace.tri.a,testFace.tri.c,testFace.tri.b)};
assert(directed(new Map([[0,[testFace]]]),new Map([[0,[reversed]]]),.03).opposed_nearest_face_samples>0);
await S.ready;
const report={
 source_sha256:baseline.source_sha256,imported_cache_sha256:baseline.imported_cache_sha256,
 source_path:baseline.source_path,mesh:0,node:'part_00006',material:primitive.material,
 dependencies:{three:'0.186.0',meshoptimizer:'1.1 bundled WASM',module_sha256:sha(fs.readFileSync('devtools/web/node_modules/three/examples/jsm/libs/meshopt_simplifier.module.js'))},
 base:{triangles:original.length/3,vertices:vertexCount,components:24,zero_area_triangles:removed.length,uv:'absent',attribute_semantics:Object.keys(primitive.attributes),locked_vertices:Array.from(locks).filter(Boolean).length},
 settings:{flags:['ErrorAbsolute','LockBorder'],target_error_m:.02,attribute_weights:[.1,.1,.1,.1,.1,.1,.1,1,1,1,1],vertex_update:false,vertex_remap:false},
 world_stretch_upper:baseline.world_stretch_upper,
 verification_method:'Bidirectional adaptive convex-patch correspondence bound with 1e-7m numerical allowance; attributes are exact stored inputs, interpolation statistics are sampled, not certified.',
 unchanged:{formal_glb:true,base_index_buffer:true,all_vertex_attribute_buffers:true,materials:true,original_lod_buffers:true,shadow_base:true},
 verifier_self_checks:{identity:true,known_displacement_rejected:true,reversed_orientation_detected:true},
 candidates:[],status:'BUILD_ONLY_GLTF_INDEX_SPACE_NOT_RENDER_VALIDATED',
 next_step:'Run map_native.mjs for full-attribute mapping and fingerprint-bound sidecar generation.'
};
const bundle={source_sha256:baseline.source_sha256,imported_cache_sha256:baseline.imported_cache_sha256,base_surface_hashes:{},shadow_surface_hashes:{},levels:[]};
for(const [dst,surf] of [[bundle.base_surface_hashes,baseline.surface],[bundle.shadow_surface_hashes,baseline.shadow_surface]])for(const key of ['vertex_data','attribute_data','index_data'])if(surf[key])dst[key]=sha(Buffer.from(surf[key][1],'hex'));
for(const target of [2000]){
 const [indices,estimated]=S.simplifyWithAttributes(clean,positions,3,attributeBuffer,11,report.settings.attribute_weights,locks,target*3,.02,report.settings.flags);
 const candidateFaces=faces(indices);
 const row={target_triangles:target,triangles:indices.length/3,simplifier_estimated_error_m:estimated};
 try {
  const cap=Math.min(.03/baseline.world_stretch_upper,Math.max(.006,estimated*2));
  row.base_to_lod=directed(baseFaces,candidateFaces,cap);
  row.lod_to_base=directed(candidateFaces,baseFaces,cap);
  row.prototype_error_upper_m=Math.max(row.base_to_lod.upper_m,row.lod_to_base.upper_m);
  row.world_error_upper_m=row.prototype_error_upper_m*baseline.world_stretch_upper;
  row.lod_edge_threshold=Math.max(row.prototype_error_upper_m,estimated)*1.000001;
  row.world_bound_le_03m=row.world_error_upper_m<=.03;
  row.handedness_preserved=row.base_to_lod.handedness_mismatches+row.lod_to_base.handedness_mismatches===0;
  row.nearest_orientation_correspondence_passed=row.base_to_lod.opposed_nearest_face_samples+row.lod_to_base.opposed_nearest_face_samples===0;
  row.triangle_reduction_percent=(1-row.triangles/(original.length/3))*100;
  row.six_observed_buckets_triangle_saving_if_selected=(original.length/3-row.triangles)*30068;
  row.default_1px_switch_distance_m=row.lod_edge_threshold*1212/(2*Math.tan(19*Math.PI/180)*(1212/900));
  row.geometry_verified=row.world_bound_le_03m&&row.handedness_preserved&&row.nearest_orientation_correspondence_passed
   &&row.base_to_lod.normal_angle_sample_deg<2&&row.lod_to_base.normal_angle_sample_deg<2
   &&row.base_to_lod.tangent_angle_sample_deg<4&&row.lod_to_base.tangent_angle_sample_deg<4
   &&row.base_to_lod.color_channel_sample_max<.0041&&row.lod_to_base.color_channel_sample_max<.0041
   &&row.prototype_error_upper_m<.007&&row.world_error_upper_m<.008;
  const file='lod-'+target+'.gltf-indices.u16';
  const packed=sourcePack(indices);
  fs.writeFileSync(path.join(out,file),packed);
  row.indices_file=file;row.indices_sha256=sha(packed);row.index_space='original glTF POSITION/NORMAL/TANGENT/COLOR_0 accessors, NOT native ArrayMesh';
  row.status=row.geometry_verified?'CANDIDATE_PENDING_NATIVE_MAPPING_AND_VISUAL_CHECK':'REJECTED_NORMAL_CORRESPONDENCE';
  if(row.geometry_verified)bundle.levels.push({...row,indices:Array.from(indices),gltf_index_hex:packed.toString('hex')});
 } catch(error){row.geometry_verified=false;row.failure=String(error);}
 report.candidates.push(row);
 console.log(JSON.stringify(row));
}
assert.equal(sha(fs.readFileSync(baseline.source_path)),baseline.source_sha256);
assert.equal(sha(fs.readFileSync(baseline.imported_cache_path)),baseline.imported_cache_sha256);
fs.writeFileSync(path.join(out,'candidate-lods.json'),JSON.stringify(bundle,null,2)+'\n');
fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2)+'\n');
console.log('REPORT',path.join(out,'report.json'));
