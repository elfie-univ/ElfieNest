import { Model, simplify, makeTree, surfaceErrors, fs, path, task, sha, assert, Matrix4 } from './geometry.mjs';

const rotation = degrees => new Matrix4().makeRotationY(degrees * Math.PI / 180);
const matrixArray = matrix => matrix.toArray().map(value => Math.abs(value) < 1e-12 ? 0 : value);
const point = (matrix, p) => {
  const e = matrix.elements, [x,y,z] = p;
  return [e[0]*x+e[4]*y+e[8]*z+e[12], e[1]*x+e[5]*y+e[9]*z+e[13], e[2]*x+e[6]*y+e[10]*z+e[14]];
};
const length = vector => Math.hypot(...vector);
const minus = (a,b) => a.map((value,k) => value-b[k]);

function hull(points) {
  const unique=new Map();
  for(const p of points) {
    const key=p.slice(0,2).map(x=>x.toFixed(6)).join(',');
    if(!unique.has(key)||unique.get(key)[2]<p[2])unique.set(key,p);
  }
  const ps=[...unique.values()].sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const lower=[],upper=[];
  for(const p of ps){while(lower.length>1&&cross(lower.at(-2),lower.at(-1),p)<=0)lower.pop();lower.push(p);}
  for(const p of ps.slice().reverse()){while(upper.length>1&&cross(upper.at(-2),upper.at(-1),p)<=0)upper.pop();upper.push(p);}
  return lower.slice(0,-1).concat(upper.slice(0,-1));
}

function sampleFrameRim(positions, indices) {
  const points=[];
  for(let i=0;i<positions.length;i+=3)points.push(Array.from(positions.subarray(i,i+3)));
  const outline=hull(points);
  function frontAt(x,y) {
    let z=-Infinity;
    for(let i=0;i<indices.length;i+=3) {
      const a=points[indices[i]],b=points[indices[i+1]],c=points[indices[i+2]];
      if(x<Math.min(a[0],b[0],c[0])-1e-7||x>Math.max(a[0],b[0],c[0])+1e-7||
         y<Math.min(a[1],b[1],c[1])-1e-7||y>Math.max(a[1],b[1],c[1])+1e-7)continue;
      const bx=b[0]-a[0],by=b[1]-a[1],cx=c[0]-a[0],cy=c[1]-a[1];
      const det=bx*cy-by*cx;
      if(Math.abs(det)<1e-12)continue;
      const u=((x-a[0])*cy-(y-a[1])*cx)/det,v=(bx*(y-a[1])-by*(x-a[0]))/det;
      if(u>=-1e-6&&v>=-1e-6&&u+v<=1+1e-6)z=Math.max(z,a[2]+u*(b[2]-a[2])+v*(c[2]-a[2]));
    }
    return z;
  }
  const center=[0,9.23], sampled=[];
  for(let i=0;i<outline.length;i++) {
    const a=outline[i],b=outline[(i+1)%outline.length];
    const count=Math.max(1,Math.ceil(Math.hypot(a[0]-b[0],a[1]-b[1])/.025));
    for(let j=0;j<count;j++) {
      const x=a[0]+(b[0]-a[0])*j/count,y=a[1]+(b[1]-a[1])*j/count;
      if(sampled.length&&Math.hypot(x-sampled.at(-1)[0],y-sampled.at(-1)[1])<.0025)continue;
      const dx=center[0]-x,dy=center[1]-y,n=Math.hypot(dx,dy);
      let next=null;
      for(let inset=.0006;inset<.055;inset+=.0007) {
        const px=x+inset*dx/n,py=y+inset*dy/n,z=frontAt(px,py);
        if(Number.isFinite(z)){next=[px,py,z];break;}
      }
      assert(next,'Cannot trace the canonical front rim');
      sampled.push(next);
    }
  }
  const nearest=makeTree(positions,indices);
  let gap=0;
  for(let i=0;i<sampled.length;i++) {
    const a=sampled[i],b=sampled[(i+1)%sampled.length];
    const midpoint=a.map((v,k)=>(v+b[k])/2);
    gap=Math.max(gap,nearest(midpoint).distance);
  }
  assert(gap<.0015,'Canonical shoulder does not hug the frame: '+gap);
  return {sampled,gap};
}

export function addWindowShoulders(model) {
  const frame=model.primitive(26);
  const {sampled:rawRim}=sampleFrameRim(model.positions(frame),model.arrays[frame.indices]);
  const shell=model.primitive(38), nearest=makeTree(model.positions(shell),model.arrays[shell.indices]);
  const positions=[], normals=[], indices=[], report=[];
  const center=[0,9.23];
  const frameNearest=makeTree(model.positions(frame),model.arrays[frame.indices]);
  const surfaces=[rawRim,...[0,1,2,3].map(q=>rawRim.map(p=>{
    const dx=p[0]/5.54,dy=(p[1]-center[1])/1.97,norm=Math.hypot(dx,dy);
    return nearest(point(rotation(90*q),[p[0]+.08*dx/norm,p[1]+.08*dy/norm,p[2]+.04])).position;
  }))];
  const kept=new Set([0,Math.floor(rawRim.length/2)]);
  function segmentDistance(p,a,b) {
    const line=minus(b,a), off=minus(p,a), dot=(a,b)=>a.reduce((sum,v,k)=>sum+v*b[k],0);
    const t=Math.max(0,Math.min(1,dot(line,off)/Math.max(1e-20,dot(line,line))));
    return length(off.map((v,k)=>v-line[k]*t));
  }
  function preserve(begin,end) {
    const index=i=>i%rawRim.length;
    let max=.00035,chosen=-1;
    for(let i=begin+1;i<end;i++) for(const points of surfaces) {
      const error=segmentDistance(points[index(i)],points[index(begin)],points[index(end)]);
      if(error>max){max=error;chosen=i;}
    }
    if(chosen>=0){kept.add(chosen);preserve(begin,chosen);preserve(chosen,end);}
  }
  const middle=Math.floor(rawRim.length/2);
  preserve(0,middle);preserve(middle,rawRim.length);
  const selected=[...kept].sort((a,b)=>a-b);
  const rim=selected.map(i=>rawRim[i]);
  let innerContactError=0;
  for(let i=0;i<rim.length;i++){
    const a=rim[i],b=rim[(i+1)%rim.length];
    innerContactError=Math.max(innerContactError,frameNearest(a.map((v,k)=>(v+b[k])/2)).distance);
  }
  assert(innerContactError<.0015,'Compressed rim lost frame contact');
  for(const quadrant of [0,1,2,3]) {
    const transform=rotation(90*quadrant), front=[], back=[];
    let gap=0,outerContactError=0;
    const projected=selected.map(i=>surfaces[quadrant+1][i]);
    for(let j=0;j<rim.length;j++) {
      const p=rim[j], projectedNext=projected[(j+1)%projected.length];
      outerContactError=Math.max(outerContactError,nearest(projected[j].map((v,k)=>(v+projectedNext[k])/2)).distance);
      const inner=point(transform,p);
      const outerPoint=projected[j].slice(), radius=Math.hypot(outerPoint[0],outerPoint[2]);
      outerPoint[0]+=.003*outerPoint[0]/radius;outerPoint[2]+=.003*outerPoint[2]/radius;
      front.push(inner,outerPoint);
      for(const v of [inner,outerPoint]) {
        const radius=Math.hypot(v[0],v[2]);
        back.push([v[0]-.008*v[0]/radius,v[1],v[2]-.008*v[2]/radius]);
      }
      gap=Math.max(gap,length(minus(inner,outerPoint)));
    }
    const base=positions.length/3, count=front.length;
    const vertices=[...front,...back];
    for(const p of vertices) {positions.push(...p);normals.push(0,0,0);}
    const face=(a,b,c) => {
      const pa=vertices[a],pb=vertices[b],pc=vertices[c];
      const u=minus(pb,pa),v=minus(pc,pa),n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
      indices.push(base+a,base+c,base+b);
      for(const id of [a,b,c])for(let k=0;k<3;k++)normals[(base+id)*3+k]-=n[k];
    };
    for(let j=0;j<rim.length;j++) {
      const a=j*2,b=(j*2+2)%count;
      face(a,b,a+1);face(a+1,b,b+1);
      face(a+count,a+count+1,b+count);face(a+count+1,b+count+1,b+count);
      face(a,a+count,b);face(b,a+count,b+count);
      face(a+1,b+1,a+count+1);face(b+1,b+count+1,a+count+1);
    }
    assert(outerContactError<.003,'Shoulder lost contact with the facade: '+outerContactError);
    report.push({quadrant:quadrant+1,shoulderWidth:.08,wallOverlap:.003,backDepth:.008,innerContactError,outerContactError,outlineVertices:rim.length,maxBridgeSpan:gap});
  }
  for(let i=0;i<normals.length;i+=3) {
    const n=Math.hypot(...normals.slice(i,i+3));
    assert(n>0,'Degenerate window shoulder');
    for(let k=0;k<3;k++)normals[i+k]/=n;
  }
  const p=model.primitive(38), oldP=model.positions(p),oldN=model.arrays[p.attributes.NORMAL],oldI=model.arrays[p.indices];
  assert.deepEqual(Object.keys(p.attributes).sort(),['NORMAL','POSITION']);
  p.attributes.POSITION=model.add(Float32Array.from([...oldP,...positions]),'VEC3',false,true);
  p.attributes.NORMAL=model.add(Float32Array.from([...oldN,...normals]),'VEC3');
  p.indices=model.add(Uint32Array.from([...oldI,...indices.map(i=>i+oldP.length/3)]),'SCALAR');
  return report;
}
