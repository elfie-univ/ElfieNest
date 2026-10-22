// Each embedded preview owns its renderer and releases it before navigation.
export function createPreviewRenderer(THREE,canvas,{antialias=true,powerPreference='low-power'}={}){
 const renderer=new THREE.WebGLRenderer({canvas,antialias,alpha:false,powerPreference,stencil:false});
 renderer.transmissionResolutionScale=1;
 return renderer;
}

export function previewLifecycle(renderer,target=window,{onRestore=()=>{}}={}){
 let released=false;
 const restored=()=>{if(!released)onRestore();};
 renderer.domElement?.addEventListener('webglcontextrestored',restored);
 function release(){
  if(released)return;
  released=true;
  renderer.domElement?.removeEventListener('webglcontextrestored',restored);
  renderer.setAnimationLoop(null);
  renderer.dispose();
  renderer.forceContextLoss();
 }
 async function prepare(scene,camera,{precompile=true}={}){
  if(precompile)await renderer.compileAsync(scene,camera);
  if(released)return false;
  renderer.render(scene,camera);
  return true;
 }
 target.addEventListener('pagehide',release,{once:true});
 return {release,prepare};
}
