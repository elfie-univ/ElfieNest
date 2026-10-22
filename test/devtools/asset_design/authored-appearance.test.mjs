import assert from 'node:assert/strict';
import {test} from 'node:test';
import * as THREE from '../../../devtools/web/node_modules/three/build/three.module.js';
import {applyAuthoredAppearance} from '../../../devtools/asset_design/web/authored-appearance.mjs';
test('untagged confirmed materials are not altered',()=>{
 const m=new THREE.MeshPhysicalMaterial({transmission:.82,roughness:.055});const before=m.toJSON();
 assert.equal(applyAuthoredAppearance(m,{}),false);assert.deepEqual(m.toJSON(),before);
});
test('trial glass retains its authored transmission tint and thickness',()=>{
 const m=new THREE.MeshPhysicalMaterial({transmission:.94,roughness:.07,thickness:.035,ior:1.46,color:0xf1fffa});m.userData.preview_surface_finish={reflectionIntensity:.8};const env=new THREE.Texture();const before=[m.transmission,m.roughness,m.thickness,m.ior,m.color.getHex()];
 assert.equal(applyAuthoredAppearance(m,env),true);assert.equal(m.envMap,env);assert.equal(m.envMapIntensity,.8);assert.deepEqual([m.transmission,m.roughness,m.thickness,m.ior,m.color.getHex()],before);assert.equal(m.transparent,false);assert.equal(m.opacity,1);
});
test('trial opaque pearl remains opaque and does not acquire emission',()=>{
 const m=new THREE.MeshPhysicalMaterial({color:0xf7f0e5,transmission:0});m.userData.preview_surface_finish={reflectionIntensity:.55};const e=m.emissive.clone();applyAuthoredAppearance(m,new THREE.Texture());assert.equal(m.transmission,0);assert.ok(m.emissive.equals(e));
});
test('thin clear glazing keeps authored alpha blending without frosting the interior',()=>{
 const m=new THREE.MeshPhysicalMaterial({transmission:0,transparent:true,opacity:.18,depthWrite:false});m.userData.preview_surface_finish={reflectionIntensity:1.05};applyAuthoredAppearance(m,new THREE.Texture());assert.equal(m.transparent,true);assert.equal(m.opacity,.18);assert.equal(m.depthWrite,false);
});
