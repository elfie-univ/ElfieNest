import {Model,makeTree,task,fs,path} from './geometry.mjs';

const results=[];
for(const [type,name] of [['main','central-building'],['pod','pod-building']]) {
  const old=new Model(path.join(task,'before',type,name+'.glb'));
  const now=new Model(path.join(task,'verified',type,name+'.glb'));
  const report=JSON.parse(fs.readFileSync(path.join(task,type+'-verified.json')));
  const targetNodes=new Map(now.doc.nodes.map(n=>[n.name,n]));
  for(const r of report.reduction.filter(r=>r.accepted)) {
    const node=old.doc.nodes.find(n=>n.mesh===r.mesh);
    const a=old.primitive(r.mesh,r.part), b=now.primitive(targetNodes.get(node.name).mesh,r.part);
    const av=old.positions(a), bv=now.positions(b);
    const ai=old.arrays[a.indices], bi=now.arrays[b.indices];
    const targetIndices=bi.subarray(0,r.candidate*3); // exclude the authored third-floor wall shoulders
    const closest=makeTree(bv,targetIndices), channels=Object.keys(a.attributes).filter(s=>s!=='POSITION');
    const errors=Object.fromEntries(channels.map(s=>[s,[]]));
    for(let i=0;i<ai.length;i+=3*Math.max(1,Math.ceil(ai.length/3/2500))){
      const source=[ai[i],ai[i+1],ai[i+2]];
      const p=[0,1,2].map(k=>source.reduce((s,v)=>s+av[v*3+k],0)/3);
      const nearest=closest(p), ids=[bi[nearest.face*3],bi[nearest.face*3+1],bi[nearest.face*3+2]];
      if(nearest.weights.some(v=>!Number.isFinite(v)||v<-.0001||v>1.0001))continue;
      for(const s of channels) {
        const left=old.arrays[a.attributes[s]],right=now.arrays[b.attributes[s]];
        const spec=old.doc.accessors[a.attributes[s]], w={VEC2:2,VEC3:3,VEC4:4}[spec.type], scale=spec.normalized?255:1;
        const from=Array.from({length:w},(_,k)=>source.reduce((sum,id)=>sum+left[id*w+k]/scale,0)/3);
        const to=Array.from({length:w},(_,k)=>ids.reduce((sum,id,v)=>sum+right[id*w+k]*nearest.weights[v]/scale,0));
        const error=s==='NORMAL' ?
          Math.acos(Math.max(-1,Math.min(1,from.reduce((sum,v,k)=>sum+v*to[k],0)/(Math.hypot(...from)*Math.hypot(...to)))))*180/Math.PI :
          Math.hypot(...from.map((v,k)=>v-to[k]));
        if(Number.isFinite(error))errors[s].push(error);
      }
    }
    const stats=Object.fromEntries(Object.entries(errors).map(([s,values])=>{
      values.sort((a,b)=>a-b);
      return [s,{samples:values.length,max:values.at(-1),p99:values[Math.floor(values.length*.99)]}];
    }));
    results.push({type,mesh:r.mesh,part:r.part,name:r.name,attributes:stats});
  }
}
fs.writeFileSync(path.join(task,'attribute-comparison.json'),JSON.stringify(results,null,2));
console.log(results.filter(r=>(r.attributes.NORMAL?.p99??0)>2||r.attributes.COLOR_0||r.attributes.TEXCOORD_0).map(r=>[r.type,r.mesh,r.part,r.attributes]));
