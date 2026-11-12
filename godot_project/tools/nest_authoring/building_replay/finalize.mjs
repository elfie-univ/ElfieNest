import { Model, fs, path, task, sha, assert } from './geometry.mjs';
import { Matrix4, Quaternion, Vector3 } from '../../../../devtools/web/node_modules/three/build/three.module.js';
import { addWindowShoulders } from './shoulders.mjs';

const baseline=JSON.parse(fs.readFileSync(path.join(task,'scene-baseline.json')));
const plan={adjustedPlacements:0};
const totals=[];
const shading=JSON.parse(fs.readFileSync(path.join(task,'attribute-comparison.json')));
for(const [type,basename] of [['main','central-building'],['pod','pod-building']]) {
  const input=path.join(task,'before',type,basename+'.glb');
  const candidate=path.join(task,'candidates',type,basename+'.glb');
  const reportPath=path.join(task,type+'-report.json');
  const report=JSON.parse(fs.readFileSync(reportPath));
  const old=new Model(input), model=new Model(candidate);
  assert.equal(sha(old.raw),report.before.sha256);
  assert.equal(sha(model.raw),report.after.sha256);
  for(const row of report.reduction.filter(r=>r.accepted)) {
    const sample=shading.find(r=>r.type===type&&r.mesh===row.mesh&&r.part===row.part)?.attributes;
    assert(sample,row.name);
    row.attributes=sample;
    if((sample.NORMAL?.p99??0)<=5&&(sample.TEXCOORD_0?.p99??0)<=.005&&(sample.COLOR_0?.p99??0)<=.01)continue;
    assert(type!=='main'||![10,14,22,26,38].includes(row.mesh),'Recheck structural surface before restoring its detail');
    row.accepted=false;
    row.reason='original shading detail preserved';
    const source=old.primitive(row.mesh,row.part), target=model.primitive(row.mesh,row.part);
    const transfer=(id,position=false)=>{
      const a=old.doc.accessors[id];
      const next=model.add(old.arrays[id],a.type,!!a.normalized,position);
      for(const property of ['min','max'])if(a[property])model.doc.accessors[next][property]=a[property].slice();
      return next;
    };
    target.attributes=Object.fromEntries(Object.entries(source.attributes).map(([s,i])=>[s,transfer(i,s==='POSITION')]));
    target.indices=transfer(source.indices);
    for(const replica of report.reuse.filter(r=>r.source===row.mesh)) {
      const instance=model.primitive(replica.target,row.part);
      instance.indices=target.indices;
      instance.attributes={...target.attributes};
    }
  }
  if(type==='main') {
    const primitive=model.primitive(38);
    const previous=report.shoulders.reduce((n,x)=>n+x.outlineVertices,0);
    for(const semantic of ['POSITION','NORMAL']) {
      const a=model.arrays[primitive.attributes[semantic]];
      primitive.attributes[semantic]=model.add(a.slice(0,a.length-previous*12),'VEC3',false,semantic==='POSITION');
    }
    const ids=model.arrays[primitive.indices];
    primitive.indices=model.add(ids.slice(0,ids.length-previous*24),'SCALAR');
    report.shoulders=addWindowShoulders(model);
  }
  const key='res://nest/buildings/'+type+'/'+basename+'.glb';
  plan[key]={};
  const byName=new Map(model.doc.nodes.map(node=>[node.name,node]));
  const materialsKey=node=>JSON.stringify(node.extras?.nest_materials??[]);
  let meshResourcesReused=0;
  for(const row of report.reuse) {
    const prototype=model.doc.nodes.find(n=>n.mesh===row.source);
    assert(prototype);
    const main=model.doc.meshes[row.source], copy=model.doc.meshes[row.target];
    const payload=m=>JSON.stringify(Object.fromEntries(Object.entries(m).filter(([key])=>key!=='name')));
    const canShareMesh=payload(main)===payload(copy) && row.bindings.every(b=>materialsKey(byName.get(b.node))===materialsKey(prototype));
    if(canShareMesh)meshResourcesReused++;
    for(const binding of row.bindings) {
      const node=byName.get(binding.node);
      const original=old.doc.nodes.find(n=>n.name===binding.node);
      assert.deepEqual(node.extras,original.extras);
      const transform=original.matrix ? new Matrix4().fromArray(original.matrix) : new Matrix4().compose(
        new Vector3(...(original.translation??[0,0,0])),
        new Quaternion(...(original.rotation??[0,0,0,1])),
        new Vector3(...(original.scale??[1,1,1]))
      );
      node.matrix=transform.multiply(new Matrix4().fromArray(binding.delta)).toArray().map(v=>Math.abs(v)<1e-12?0:v);
      assert(node.matrix.every(Number.isFinite),binding.node);
      if(canShareMesh)node.mesh=row.source;
      const placed=baseline.placements[key+':'+binding.node];
      assert(placed?.length&&placed.every(n=>n.class==='MeshInstance3D'),binding.node);
      plan.adjustedPlacements+=placed.length;
      plan[key][binding.node]={prototype:prototype.name,delta:binding.delta,sourceTransform:node.matrix};
    }
  }
  const live=[...new Set(model.doc.nodes.map(n=>n.mesh).filter(i=>i!==undefined))].sort((a,b)=>a-b);
  const map=new Map(live.map((i,index)=>[i,index]));
  model.doc.meshes=live.map(i=>model.doc.meshes[i]);
  for(const node of model.doc.nodes)if(node.mesh!==undefined)node.mesh=map.get(node.mesh);
  const final=path.join(task,'verified',type,basename+'.glb');
  const after=model.save(final);
  const reloaded=new Model(final);
  const counts=model=>{
    const unique=new Map();
    let rendered=0;
    for(const node of model.doc.nodes)if(node.mesh!==undefined)for(const part of model.doc.meshes[node.mesh].primitives){
      const count=model.arrays[part.indices].length/3;
      const key=[part.indices,...Object.entries(part.attributes).sort().map(([s,i])=>s+':'+i)].join(',');
      unique.set(key,count);rendered+=count;
    }
    return {storedTriangles:[...unique.values()].reduce((s,n)=>s+n,0),trianglesIncludingPlacements:rendered};
  };
  function degenerate(model,part) {
    const positions=model.positions(part),indices=model.arrays[part.indices];
    let n=0;
    for(let i=0;i<indices.length;i+=3) {
      const a=3*indices[i],b=3*indices[i+1],c=3*indices[i+2];
      assert(Math.max(a,b,c)+2<positions.length);
      const x=positions[b]-positions[a],y=positions[b+1]-positions[a+1],z=positions[b+2]-positions[a+2];
      const u=positions[c]-positions[a],v=positions[c+1]-positions[a+1],w=positions[c+2]-positions[a+2];
      if(y*w-z*v===0&&z*u-x*w===0&&x*v-y*u===0)n++;
    }
    return n;
  }
  let oldDegenerate=0,newDegenerate=0;
  for(const mesh of old.doc.meshes)for(const part of mesh.primitives)oldDegenerate+=degenerate(old,part);
  for(const mesh of reloaded.doc.meshes)for(const part of mesh.primitives)newDegenerate+=degenerate(reloaded,part);
  assert(newDegenerate<=oldDegenerate);
  for(const array of reloaded.arrays)if(array instanceof Float32Array)assert(array.every(Number.isFinite));
  for(const key of ['materials','textures','samplers','images','scenes','extensionsUsed','extensionsRequired'])
    assert.deepEqual(reloaded.doc[key],old.doc[key],key);
  for(const [i,node] of reloaded.doc.nodes.entries()) {
    const {mesh:_,matrix:__,translation:___,rotation:____,scale:_____,...identity}=node;
    const {mesh:omit,matrix:m,translation:t,rotation:r,scale:s,...source}=old.doc.nodes[i];
    assert.deepEqual(identity,source);
    if(node.matrix)assert(node.matrix.length===16&&node.matrix.every(Number.isFinite),node.name);
    if(!plan['res://nest/buildings/'+type+'/'+basename+'.glb'][node.name]){
      assert.deepEqual([node.matrix,node.translation,node.rotation,node.scale],[m,t,r,s]);
    }
  }
  report.before={...report.before,...counts(old)};
  report.after={...after,...reloaded.metrics(),...counts(reloaded)};
  report.meshResourcesReused=meshResourcesReused;
  report.oldDegenerateFaces=oldDegenerate;
  report.newDegenerateFaces=newDegenerate;
  fs.writeFileSync(path.join(task,type+'-verified.json'),JSON.stringify(report,null,2));
  const total={type,before:report.before,after:report.after,reuse:report.reuse.length,meshResourcesReused,shoulders:report.shoulders};
  totals.push(total);console.log(JSON.stringify(total));
}
fs.writeFileSync(path.join(task,'placement-plan.json'),JSON.stringify(plan,null,2));
fs.writeFileSync(path.join(task,'summary.json'),JSON.stringify(totals,null,2));
