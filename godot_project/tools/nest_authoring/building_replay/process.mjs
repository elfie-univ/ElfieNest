import { Model, simplify, makeTree, surfaceErrors, fs, path, task, sha, assert, Matrix4 } from './geometry.mjs';

const rotation = degrees => new Matrix4().makeRotationY(degrees * Math.PI / 180);
const matrixArray = matrix => matrix.toArray().map(value => Math.abs(value) < 1e-12 ? 0 : value);
const point = (matrix, p) => {
  const e = matrix.elements, [x,y,z] = p;
  return [e[0]*x+e[4]*y+e[8]*z+e[12], e[1]*x+e[5]*y+e[9]*z+e[13], e[2]*x+e[6]*y+e[10]*z+e[14]];
};
const length = vector => Math.hypot(...vector);
const minus = (a,b) => a.map((value,k) => value-b[k]);

function centeredOrientation(model, mesh) {
  const points = model.doc.meshes[mesh].primitives.flatMap(p => Array.from(model.positions(p)));
  const center = [0,0,0];
  for (let i=0;i<points.length;i++) center[i%3] += points[i]/(points.length/3);
  let xx=0, zz=0, xz=0;
  for (let i=0;i<points.length;i+=3) {
    const x=points[i]-center[0], z=points[i+2]-center[2];
    xx+=x*x; zz+=z*z; xz+=x*z;
  }
  return { center, yaw: Math.atan2(2*xz,xx-zz)/2 };
}

function fit(model, source, target) {
  const src=model.doc.meshes[source].primitives, dst=model.doc.meshes[target].primitives;
  if (src.length!==dst.length) return null;
  const material=id => {
    const m=structuredClone(model.doc.materials[id]);
    delete m.name; return JSON.stringify(m);
  };
  for(let p=0;p<src.length;p++) if(material(src[p].material)!==material(dst[p].material)) return null;
  const a=centeredOrientation(model,source), b=centeredOrientation(model,target);
  const angles = [...new Set([0,90,180,270,120,-120,...[0,90,180,270].map(x => (a.yaw-b.yaw)*180/Math.PI+x)].map(x=>Math.round(x*1e6)/1e6))];
  const epsilon=.0004;
  for (const angle of angles) {
    const transform=rotation(angle), rotated=point(transform,a.center);
    transform.setPosition(...minus(b.center,rotated));
    let valid=true, maxPosition=0, maxNormal=0, maxUV=0;
    for(let pi=0;pi<src.length&&valid;pi++) {
      const sp=src[pi],tp=dst[pi], ps=model.positions(sp),pt=model.positions(tp);
      if(ps.length!==pt.length) {valid=false;break;}
      const normalS=model.arrays[sp.attributes.NORMAL], normalT=model.arrays[tp.attributes.NORMAL];
      const uvS=model.arrays[sp.attributes.TEXCOORD_0], uvT=model.arrays[tp.attributes.TEXCOORD_0];
      const grid=new Map(), key=p=>p.join(',');
      for(let i=0;i<pt.length;i+=3) {
        const cell=key([0,1,2].map(k=>Math.floor(pt[i+k]/epsilon)));
        if(!grid.has(cell)) grid.set(cell,[]);
        grid.get(cell).push(i/3);
      }
      const mapping=new Int32Array(ps.length/3).fill(-1);
      for(let i=0;i<ps.length&&valid;i+=3) {
        const p=point(transform,ps.subarray(i,i+3)),cell=p.map(x=>Math.floor(x/epsilon));
        const ns=point(rotation(angle),normalS.subarray(i,i+3));
        let best=-1,score=Infinity, pe,ne,ue;
        for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++) {
          for(const j of grid.get(key([cell[0]+x,cell[1]+y,cell[2]+z]))??[]) {
            const posError=length(minus(p,pt.subarray(j*3,j*3+3)));
            const normalError=length(minus(ns,normalT.subarray(j*3,j*3+3)));
            const uvError=uvS?length(minus(uvS.subarray(i/3*2,i/3*2+2),uvT.subarray(j*2,j*2+2))):0;
            const error=posError+normalError*.001+uvError*.001;
            if(posError<=epsilon&&normalError<=.02&&uvError<=.001&&error<score) {
              best=j;score=error;pe=posError;ne=normalError;ue=uvError;
            }
          }
        }
        if(best<0)valid=false;
        else {mapping[i/3]=best;maxPosition=Math.max(maxPosition,pe);maxNormal=Math.max(maxNormal,ne);maxUV=Math.max(maxUV,ue);}
      }
      if(!valid) break;
      const si=model.arrays[sp.indices],ti=model.arrays[tp.indices];
      const faceKey=ids => {
        const [a,b,c]=ids;return (a<=b&&a<=c?[a,b,c]:b<=a&&b<=c?[b,c,a]:[c,a,b]).join(',');
      };
      const faces=new Map();
      for(let i=0;i<ti.length;i+=3) {
        const key=faceKey(ti.subarray(i,i+3));faces.set(key,(faces.get(key)??0)+1);
      }
      for(let i=0;i<si.length;i+=3) {
        const key=faceKey(Array.from(si.subarray(i,i+3),v=>mapping[v]));
        if(!faces.get(key)) {valid=false;break;}
        faces.set(key,faces.get(key)-1);
      }
    }
    if(valid) return { source, target, matrix:matrixArray(transform), maxPosition, maxNormal, maxUV, kind:'measured-rigid-reuse' };
  }
  return null;
}

function findReuse(model,isMain) {
  const rows=[], assigned=new Set(), manualSources=new Set();
  if(isMain) {
    for(const [source,targets] of [[10,[11,12,13]],[14,[15,16,17]],[22,[23,24,25]],[26,[27,28,29]]]) {
      manualSources.add(source);
      for(const [i,target] of targets.entries()) {
        rows.push({source,target,matrix:matrixArray(rotation((i+1)*90)),kind:source>=22?'standardized-third-floor-window':'standardized-second-floor-window'});
        assigned.add(target);
      }
    }
    for(const [target,angle] of [[439,120],[440,-120]]) {
      rows.push({source:438,target,matrix:matrixArray(rotation(angle)),kind:'standardized-roof-petal'});
      assigned.add(target);
    }
  }
  const groups=new Map();
  for(const [i,mesh] of model.doc.meshes.entries()) {
    if(assigned.has(i)||manualSources.has(i)||/door|sliding leaf/i.test(model.sourceName(i))) continue;
    const key=mesh.primitives.map(p => [model.arrays[p.indices].length,model.positions(p).length,Object.keys(p.attributes).sort().join(',')].join(':')).join('/');
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(i);
  }
  for(const group of groups.values()) {
    const prototypes=[];
    for(const target of group) {
      let row=null;
      for(const source of prototypes) {row=fit(model,source,target);if(row)break;}
      if(row) {rows.push(row);assigned.add(target);}
      else prototypes.push(target);
    }
  }
  return rows;
}

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

function addWindowShoulders(model, old) {
  const frame=model.primitive(26);
  const {sampled:rim,gap:innerContactError}=sampleFrameRim(model.positions(frame),model.arrays[frame.indices]);
  const shell=model.primitive(38), nearest=makeTree(model.positions(shell),model.arrays[shell.indices]);
  const positions=[], normals=[], indices=[], report=[];
  const center=[0,9.23];
  for(const quadrant of [0,1,2,3]) {
    const transform=rotation(90*quadrant), front=[], back=[];
    let gap=0;
    for(const p of rim) {
      const dx=(p[0]-center[0])/5.54,dy=(p[1]-center[1])/1.97, norm=Math.hypot(dx,dy);
      const expanded=[p[0]+.08*dx/norm,p[1]+.08*dy/norm,p[2]+.04];
      const outer=nearest(point(transform,expanded));
      const inner=point(transform,p);
      const outerPoint=outer.position.slice(), radius=Math.hypot(outerPoint[0],outerPoint[2]);
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
      indices.push(base+a,base+b,base+c);
      for(const id of [a,b,c])for(let k=0;k<3;k++)normals[(base+id)*3+k]+=n[k];
    };
    for(let j=0;j<rim.length;j++) {
      const a=j*2,b=(j*2+2)%count;
      face(a,b,a+1);face(a+1,b,b+1);
      face(a+count,a+count+1,b+count);face(a+count+1,b+count+1,b+count);
      face(a,a+count,b);face(b,a+count,b+count);
      face(a+1,b+1,a+count+1);face(b+1,b+count+1,a+count+1);
    }
    report.push({quadrant:quadrant+1,shoulderWidth:.08,wallOverlap:.003,backDepth:.008,innerContactError,outlineVertices:rim.length,maxBridgeSpan:gap});
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

for(const type of ['pod','main']) {
  const basename=type==='main'?'central-building.glb':'pod-building.glb';
  const file=path.join(task,'before',type,basename);
  const model=new Model(file), old=new Model(file), before=model.metrics();
  const reuse=findReuse(model,type==='main'), targets=new Set(reuse.map(r=>r.target)), reduction=[];
  fs.writeFileSync(path.join(task,type+'-reuse.json'),JSON.stringify(reuse,null,2));
  console.log('REUSE_PLAN',type,reuse.length);
  for(const [mesh,record] of model.doc.meshes.entries()) {
    if(targets.has(mesh))continue;
    for(let part=0;part<record.primitives.length;part++) {
      const name=model.sourceName(mesh);
      const threshold=/full-height envelope|sculpted continuous shell/i.test(name) ? .002 : /glass|glazing|light|diffuser|strip/i.test(name) ? .0005 : .001;
      await simplify(model,mesh,part,reduction,threshold);
      const last=reduction.at(-1);
      if(last?.mesh===mesh&&last?.part===part)console.log('REDUCTION',type,JSON.stringify(last));
    }
  }
  const shoulders=type==='main'?addWindowShoulders(model,old):[];
  for(const row of reuse) {
    const src=model.doc.meshes[row.source].primitives,dst=model.doc.meshes[row.target].primitives;
    assert.equal(src.length,dst.length);
    for(let i=0;i<src.length;i++) {dst[i].attributes={...src[i].attributes};dst[i].indices=src[i].indices;}
    row.bindings=[];
    for(const node of model.doc.nodes.filter(node=>node.mesh===row.target)) {
      const original=node.matrix??new Matrix4().compose(
        {x:node.translation?.[0]??0,y:node.translation?.[1]??0,z:node.translation?.[2]??0},
        {x:node.rotation?.[0]??0,y:node.rotation?.[1]??0,z:node.rotation?.[2]??0,w:node.rotation?.[3]??1},
        {x:node.scale?.[0]??1,y:node.scale?.[1]??1,z:node.scale?.[2]??1}
      ).toArray();
      row.bindings.push({node:node.name,path:node.extras?.v044_path,delta:row.matrix});
      node.matrix=matrixArray(new Matrix4().fromArray(original).multiply(new Matrix4().fromArray(row.matrix)));
      delete node.translation;delete node.rotation;delete node.scale;
    }
  }
  const after=model.save(path.join(task,'candidates',type,basename));
  const report={type,before:{bytes:old.raw.length,sha256:sha(old.raw),...before},after:{...after,...model.metrics()},reuse,reduction,shoulders};
  fs.writeFileSync(path.join(task,type+'-report.json'),JSON.stringify(report,null,2));
  console.log('CANDIDATE_DONE',type,JSON.stringify({...after,reuse:reuse.length,accepted:reduction.filter(r=>r.accepted).length}));
}
