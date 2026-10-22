import assert from 'node:assert/strict';
import {test} from 'node:test';
import * as THREE from '../../../devtools/web/node_modules/three/build/three.module.js';
import {installLightShaderLoops} from '../../../devtools/asset_design/web/light-shader-loops.mjs';

test('all 83 fixture lights remain in dynamically bounded lighting loops',()=>{
 const material=new THREE.MeshPhysicalMaterial();
 installLightShaderLoops([material],THREE);
 const spots=Array.from({length:82},()=>({})),points=[{}];
 const shader={fragmentShader:'#include <lights_fragment_begin>',uniforms:{spotLights:{value:spots},pointLights:{value:points}}};
 material.onBeforeCompile(shader,{});
 assert.equal(shader.uniforms.previewSpotLightCount.value,82);
 assert.equal(shader.uniforms.previewPointLightCount.value,1);
 assert.match(shader.fragmentShader,/i < previewSpotLightCount/);
 assert.match(shader.fragmentShader,/i < previewPointLightCount/);
 assert.match(shader.fragmentShader,/getSpotLightInfo\( spotLight, geometryPosition, directLight \)/);
 assert.match(shader.fragmentShader,/RE_Direct\( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight \)/);
 shader.uniforms.spotLights.value=spots.slice(0,25);
 assert.equal(shader.uniforms.previewSpotLightCount.value,25);
 assert.equal(spots.length+points.length,83);
});

test('shadowed and mapped lights retain the original Three shader branch',()=>{
 const material=new THREE.MeshStandardMaterial();installLightShaderLoops([material],THREE);
 const shader={fragmentShader:'#include <lights_fragment_begin>',uniforms:{spotLights:{value:[]},pointLights:{value:[]}}};material.onBeforeCompile(shader,{});
 assert.match(shader.fragmentShader,/#if NUM_SPOT_LIGHT_SHADOWS == 0 && NUM_SPOT_LIGHT_MAPS == 0/);
 assert.match(shader.fragmentShader,/spotShadowMap\[ i \]/);
 assert.match(shader.fragmentShader,/spotLightMap\[ SPOT_LIGHT_MAP_INDEX \]/);
 assert.match(shader.fragmentShader,/NUM_POINT_LIGHT_SHADOWS == 0/);
});

test('installing hooks twice neither chains duplicate patches nor changes material values',()=>{
 const material=new THREE.MeshStandardMaterial({color:0xffeecc,roughness:.78});const original=material.toJSON();let previous=0;material.onBeforeCompile=()=>{previous++;};
 installLightShaderLoops([material,material],THREE);
 const shader={fragmentShader:'#include <lights_fragment_begin>',uniforms:{spotLights:{value:[]},pointLights:{value:[]}}};material.onBeforeCompile(shader,{});
 assert.equal(previous,1);assert.deepEqual(material.toJSON(),original);
 assert.equal(shader.fragmentShader.split('uniform int previewSpotLightCount;').length-1,1);
});

test('combined preview packs every light without losing optics or camera-space updates',()=>{
 const material=new THREE.MeshPhysicalMaterial();installLightShaderLoops([material],THREE);
 const point={position:new THREE.Vector3(1,2,3),color:new THREE.Color(1,.5,.25),distance:8,decay:2};
 const spot={...point,direction:new THREE.Vector3(0,-1,0),coneCos:.75,penumbraCos:.875};
 const spots=Array.from({length:160},(_,i)=>({...spot,position:new THREE.Vector3(i,2,3)}));
 const shader={fragmentShader:'#include <lights_pars_begin>\n#include <lights_fragment_begin>',uniforms:{pointLights:{value:[point]},spotLights:{value:spots}}};
 material.onBeforeCompile(shader,{});
 assert.equal(shader.uniforms.previewSpotLightCount.value,160);
 const packed=shader.uniforms.previewPackedSpotLights.value;
 assert.equal(packed.length,160*16);
 assert.deepEqual([...packed.slice(16,32)],[1,2,3,8,1,.5,.25,2,0,-1,0,.75,.875,0,0,0]);
 assert.deepEqual([...shader.uniforms.previewPackedPointLights.value],[1,2,3,8,1,.5,.25,2]);
 spots[1].position.set(9,8,7);
 assert.strictEqual(shader.uniforms.previewPackedSpotLights.value,packed);
 assert.deepEqual([...packed.slice(16,19)],[9,8,7]);
 assert.match(shader.fragmentShader,/uniform vec4 previewPackedSpotLights\[ NUM_SPOT_LIGHTS \* 4 \]/);
 assert.match(shader.fragmentShader,/previewReadSpotLight\( i, spotLight \)/);
 assert.match(shader.fragmentShader,/#else\s+uniform SpotLight spotLights\[ NUM_SPOT_LIGHTS \]/);
 assert.equal(shader.uniforms.spotLights.value,spots,'Three still owns the original light state');
});

test('zero-contribution lights skip BRDF work without reducing light count or attenuation',()=>{
 const material=new THREE.MeshPhysicalMaterial();installLightShaderLoops([material],THREE);
 const shader={fragmentShader:'#include <lights_fragment_begin>',uniforms:{spotLights:{value:Array(160).fill({})},pointLights:{value:[]}}};material.onBeforeCompile(shader,{});
 for(const kind of ['Spot','Point'])assert.match(shader.fragmentShader,new RegExp(`get${kind}LightInfo\\([^;]+;\\s+if \\( directLight.visible \\) \\{\\s+RE_Direct`));
 assert.equal(shader.uniforms.previewSpotLightCount.value,160);
});

test('materials reuse one packed light upload per renderer frame and refresh on the next frame',()=>{
 const renderer={info:{render:{frame:1}}},lights=[{position:new THREE.Vector3(1,2,3),color:new THREE.Color(.5,.5,.5),distance:8,decay:2}];
 const shaders=Array.from({length:2},()=>{const material=new THREE.MeshStandardMaterial();installLightShaderLoops([material],THREE);const shader={fragmentShader:'#include <lights_pars_begin>\n#include <lights_fragment_begin>',uniforms:{pointLights:{value:lights},spotLights:{value:[]}}};material.onBeforeCompile(shader,renderer);return shader;});
 const first=shaders[0].uniforms.previewPackedPointLights.value;
 assert.strictEqual(shaders[1].uniforms.previewPackedPointLights.value,first);
 lights[0].position.x=7;renderer.info.render.frame++;
 assert.equal(shaders[1].uniforms.previewPackedPointLights.value[0],7);
 assert.strictEqual(shaders[0].uniforms.previewPackedPointLights.value,first);
});

test('finite-range light rejection precedes normalization and attenuation; unlimited lights stay active',()=>{
 const material=new THREE.MeshStandardMaterial();installLightShaderLoops([material],THREE);
 const shader={fragmentShader:'#include <lights_fragment_begin>',uniforms:{spotLights:{value:[]},pointLights:{value:[]}}};material.onBeforeCompile(shader,{});
 for(const kind of ['Spot','Point']){
  const start=shader.fragmentShader.indexOf(`i < preview${kind}LightCount`),end=shader.fragmentShader.indexOf('#else',start),loop=shader.fragmentShader.slice(start,end);
  assert.match(loop,/previewRange\.w > 0\.0/);
  assert.match(loop,/dot\( previewDelta, previewDelta \) > previewRange\.w \* previewRange\.w/);
  assert.ok(loop.indexOf('continue;')<loop.indexOf(`get${kind}LightInfo`));
 }
 const attenuation=THREE.ShaderChunk.lights_pars_begin;
 assert.match(attenuation,/pow2\( saturate\( 1\.0 - pow4\( lightDistance \/ cutoffDistance \) \) \)/);
});

test('packed light arrays upload once per program and frame, with distinct light sets kept independent',()=>{
 const programA={},programB={},renderer={info:{render:{frame:1}},properties:new WeakMap()};
 const lights=[{position:new THREE.Vector3(1,2,3),color:new THREE.Color(.5,.5,.5),distance:8,decay:2}];
 const make=()=>{const material=new THREE.MeshStandardMaterial();renderer.properties.set(material,{currentProgram:programA});installLightShaderLoops([material],THREE);const shader={fragmentShader:'#include <lights_pars_begin>\n#include <lights_fragment_begin>',uniforms:{pointLights:{value:lights},spotLights:{value:[]}}};material.onBeforeCompile(shader,renderer);return {material,shader};};
 const a=make(),b=make(),ua=a.shader.uniforms.previewPackedPointLights,ub=b.shader.uniforms.previewPackedPointLights;
 assert.equal(ua.needsUpdate,true);const first=ua.value;
 assert.equal(ub.needsUpdate,false,'same GPU program already has these light values');
 renderer.properties.get(b.material).currentProgram=programB;
 assert.equal(ub.needsUpdate,true);assert.strictEqual(ub.value,first);
 renderer.info.render.frame++;lights[0].position.x=9;
 assert.equal(ua.needsUpdate,true);assert.equal(ua.value[0],9);
 renderer.properties.get(b.material).currentProgram=programA;
 b.shader.uniforms.pointLights.value=lights.slice();
 assert.equal(ub.needsUpdate,true,'another light state must replace the previous upload');void ub.value;
 assert.equal(ua.needsUpdate,true,'switching back restores the original light state');
});
