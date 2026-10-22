// Keep unshadowed fixture evaluation and uniform storage compact in combined views.
// Shadow/map sampler indexing still uses Three's original constant-index loops.
const installed=new WeakSet();
const framePacks=new WeakMap();
// Uniform arrays bypass Three's scalar-value cache. A shared GPU program keeps
// its light values across material switches; upload again for each frame/light set.
const programUploads=new WeakMap();
function packedLights(shader,kind,rows,renderer,material){
 let packed=new Float32Array(0);
 return {get needsUpdate(){
  const program=renderer?.properties?.get(material)?.currentProgram,frame=renderer?.info?.render.frame;
  if(!program||!Number.isInteger(frame))return true;
  const previous=programUploads.get(program)?.[kind];
  return previous?.frame!==frame||previous.lights!==shader.uniforms[`${kind}Lights`]?.value;
 },get value(){
  const program=renderer?.properties?.get(material)?.currentProgram,uploadFrame=renderer?.info?.render.frame;
  if(program&&Number.isInteger(uploadFrame)){
   let uploads=programUploads.get(program);
   if(!uploads){uploads={};programUploads.set(program,uploads);}
   uploads[kind]={frame:uploadFrame,lights:shader.uniforms[`${kind}Lights`]?.value};
  }
  const lights=shader.uniforms[`${kind}Lights`]?.value||[];
  const frame=renderer?.info?.render.frame,cached=framePacks.get(lights);
  if(Number.isInteger(frame)&&cached?.renderer===renderer&&cached.frame===frame&&cached.packed.length===lights.length*rows*4)return cached.packed;
  if(cached?.renderer===renderer)packed=cached.packed;
  if(packed.length!==lights.length*rows*4)packed=new Float32Array(lights.length*rows*4);
  lights.forEach((light,i)=>{
   const offset=i*rows*4;
   packed.set([light.position.x,light.position.y,light.position.z,light.distance,
    light.color.r,light.color.g,light.color.b,light.decay],offset);
   if(kind==='spot')packed.set([light.direction.x,light.direction.y,light.direction.z,light.coneCos,
    light.penumbraCos,0,0,0],offset+8);
  });
  if(Number.isInteger(frame))framePacks.set(lights,{renderer,frame,packed});
  return packed;
 }};
}
export function installLightShaderLoops(materials,THREE){
 let chunk=THREE.ShaderChunk.lights_fragment_begin;
 let declarations=THREE.ShaderChunk.lights_pars_begin;
 for(const [kind,guard] of [['Point','NUM_POINT_LIGHT_SHADOWS == 0'],['Spot','NUM_SPOT_LIGHT_SHADOWS == 0 && NUM_SPOT_LIGHT_MAPS == 0']]){
  const upper=kind.toUpperCase(),lower=kind.toLowerCase();
  const rows=kind==='Point'?2:4;
  const declaration=`uniform ${kind}Light ${lower}Lights[ NUM_${upper}_LIGHTS ];`;
  if(!declarations.includes(declaration))throw new Error(`Unsupported Three ${kind} light uniforms`);
  declarations=declarations.replace(declaration,`#if ${guard}
 uniform vec4 previewPacked${kind}Lights[ NUM_${upper}_LIGHTS * ${rows} ];
 void previewRead${kind}Light( const in int i, out ${kind}Light light ) {
  vec4 positionDistance = previewPacked${kind}Lights[ i * ${rows} ];
  vec4 colorDecay = previewPacked${kind}Lights[ i * ${rows} + 1 ];
  light.position = positionDistance.xyz;
  light.distance = positionDistance.w;
  light.color = colorDecay.xyz;
  light.decay = colorDecay.w;
  ${kind==='Spot'?`vec4 directionCone = previewPackedSpotLights[ i * 4 + 2 ];
  light.direction = directionCone.xyz;
  light.coneCos = directionCone.w;
  light.penumbraCos = previewPackedSpotLights[ i * 4 + 3 ].x;`:''}
 }
 #else
 ${declaration}
 #endif`);
  const pattern=new RegExp(`#pragma unroll_loop_start\\s+for \\( int i = 0; i < NUM_${upper}_LIGHTS; i \\+\\+ \\) \\{[\\s\\S]*?#pragma unroll_loop_end`);
  if(!pattern.test(chunk))throw new Error(`Unsupported Three ${kind} light shader loop`);
  chunk=chunk.replace(pattern,original=>`#if ${guard}
 for ( int i = 0; i < preview${kind}LightCount; i ++ ) {
  vec4 previewRange = previewPacked${kind}Lights[ i * ${rows} ];
  vec3 previewDelta = previewRange.xyz - geometryPosition;
  // Three's finite cutoff is exactly zero beyond this radius. Reject before
  // normalization and attenuation; unlimited lights keep the original path.
  if ( previewRange.w > 0.0 && dot( previewDelta, previewDelta ) > previewRange.w * previewRange.w ) continue;
  previewRead${kind}Light( i, ${lower}Light );
  get${kind}LightInfo( ${lower}Light, geometryPosition, directLight );
  if ( directLight.visible ) {
   RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
  }
 }
 #else
 ${original}
 #endif`);
 }
 for(const material of materials){
  if(!material?.isMeshStandardMaterial||installed.has(material))continue;
  installed.add(material);
  const previous=material.onBeforeCompile,cacheKey=material.customProgramCacheKey;
  material.onBeforeCompile=function(shader,renderer){
   previous.call(this,shader,renderer);
   if(!shader.fragmentShader.includes('#include <lights_fragment_begin>'))return;
   for(const kind of ['Point','Spot']){
    shader.uniforms[`preview${kind}LightCount`]={get value(){return shader.uniforms[`${kind.toLowerCase()}Lights`]?.value.length||0;}};
    shader.uniforms[`previewPacked${kind}Lights`]=packedLights(shader,kind.toLowerCase(),kind==='Point'?2:4,renderer,this);
   }
   shader.fragmentShader='uniform int previewPointLightCount;\nuniform int previewSpotLightCount;\n'+shader.fragmentShader.replace('#include <lights_pars_begin>',declarations).replace('#include <lights_fragment_begin>',chunk);
  };
  material.customProgramCacheKey=function(){return cacheKey.call(this)+';preview-light-loops-v4-range';};
  material.needsUpdate=true;
 }
}
