import assert from 'node:assert/strict';
import {test} from 'node:test';
import * as THREE from '../../../devtools/web/node_modules/three/build/three.module.js';
import {attachFixtureLights,updateFixtureLights} from '../../../devtools/asset_design/web/fixture-lights.mjs';

test('asset lights retain fixture transforms, visibility and independent day/night intensity',()=>{
 const mesh=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({emissive:0xffffff}));
 mesh.position.set(4,8,2);mesh.userData={design_lights:[{type:'spot',position:[0,-.1,0],target:[1,-2,0],intensity:30,distance:3,angle:.9}],lighting_diffuser:true};
 const entries=attachFixtureLights(mesh,THREE);mesh.updateMatrixWorld(true);
 assert.equal(entries.length,1);const light=entries[0].light;
 assert.deepEqual(light.getWorldPosition(new THREE.Vector3()).toArray(),[4,7.9,2]);
 assert.deepEqual(light.target.getWorldPosition(new THREE.Vector3()).toArray(),[5,6,2]);
 mesh.visible=false;updateFixtureLights(entries,true);assert.equal(light.visible,false);
 mesh.visible=true;updateFixtureLights(entries,true);assert.equal(light.visible,true);assert.equal(light.intensity,30);
 updateFixtureLights(entries,false);assert.equal(light.intensity,2.4);
 assert.equal(mesh.material.emissiveIntensity,.15);
 assert.throws(()=>attachFixtureLights({userData:{design_lights:[{type:'spot',position:[0,NaN,0]}]}},THREE),/灯具/);
});
