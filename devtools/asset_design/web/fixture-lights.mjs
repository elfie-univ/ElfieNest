// Lamp positions and optics belong to the asset, in its own node coordinates.
export function attachFixtureLights(mesh,THREE){
 const definitions=mesh.userData.design_lights||[],entries=[];
 const vector=value=>Array.isArray(value)&&value.length===3&&value.every(Number.isFinite);
 if(!Array.isArray(definitions))throw new Error('灯具光源数据无效');
 for(const value of definitions){
  if(!['point','spot'].includes(value.type)||!vector(value.position)||!Number.isFinite(value.intensity)||value.intensity<0||!Number.isFinite(value.distance)||value.distance<=0||value.type==='spot'&&(!vector(value.target)||!Number.isFinite(value.angle)||value.angle<=0||value.angle>=Math.PI/2))throw new Error('灯具光源数据无效');
  const light=value.type==='spot'?new THREE.SpotLight(value.color??0xffdfb5,value.intensity,value.distance,value.angle,1,2):new THREE.PointLight(value.color??0xffdfb5,value.intensity,value.distance,2);
  light.position.fromArray(value.position);mesh.add(light);
  if(value.type==='spot'){light.target.position.fromArray(value.target);mesh.add(light.target);}
  entries.push({mesh,light,intensity:value.intensity});
 }
 if(mesh.userData.lighting_diffuser){
  mesh.material=Array.isArray(mesh.material)?mesh.material.map(m=>m.clone()):mesh.material.clone();
 }
 return entries;
}
export function updateFixtureLights(entries,dusk){
 for(const {mesh,light,intensity} of entries){
  light.visible=mesh.visible;light.intensity=intensity*(dusk?1:.08);
  if(mesh.userData.lighting_diffuser)for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material])material.emissiveIntensity=dusk?1:.15;
 }
}
