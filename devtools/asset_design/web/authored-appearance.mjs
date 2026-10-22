// Opt-in surfaces retain glTF optics; existing confirmed materials use the normal viewer finish.
export function applyAuthoredAppearance(material,environment){
 const finish=material.userData?.preview_surface_finish;
 if(!finish)return false;
 const intensity=finish.reflectionIntensity;
 if(!Number.isFinite(intensity)||intensity<0||intensity>2)throw new Error('Invalid authored reflection intensity');
 material.envMap=environment;
 material.envMapIntensity=intensity;
 return true;
}

export function createAuthoredEnvironment(THREE,renderer){
 const canvas=document.createElement('canvas');canvas.width=512;canvas.height=256;
 const context=canvas.getContext('2d');
 const sky=context.createLinearGradient(0,0,0,256);
 sky.addColorStop(0,'#e6e4f0');sky.addColorStop(.42,'#9caab5');sky.addColorStop(.55,'#535d66');sky.addColorStop(1,'#756555');
 context.fillStyle=sky;context.fillRect(0,0,512,256);
 for(const [x,y,w,h,rgb] of [[45,128,130,180,'90,215,242'],[250,128,110,170,'209,160,245'],[450,128,120,170,'255,213,162']]){
  const glow=context.createRadialGradient(x,y,0,x,y,w);
  glow.addColorStop(0,`rgba(${rgb},.9)`);glow.addColorStop(.55,`rgba(${rgb},.4)`);glow.addColorStop(1,`rgba(${rgb},0)`);
  context.save();context.translate(x,y);context.scale(1,h/w);context.translate(-x,-y);context.fillStyle=glow;context.fillRect(x-w,y-w,w*2,w*2);context.restore();
 }
 const texture=new THREE.CanvasTexture(canvas);texture.mapping=THREE.EquirectangularReflectionMapping;texture.colorSpace=THREE.SRGBColorSpace;
 const generator=new THREE.PMREMGenerator(renderer);const target=generator.fromEquirectangular(texture);texture.dispose();generator.dispose();
 return target;
}
