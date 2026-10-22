import assert from 'node:assert/strict';
import {test} from 'node:test';
import {previewLifecycle} from '../../../devtools/asset_design/web/preview-lifecycle.mjs';

test('leaving a preview stops rendering and releases its WebGL context exactly once',()=>{
 const target=new EventTarget(),events=[];
 const renderer={setAnimationLoop:value=>events.push(['loop',value]),dispose:()=>events.push(['dispose']),forceContextLoss:()=>events.push(['release-context'])};
 const {release}=previewLifecycle(renderer,target);
 assert.deepEqual(events,[]);
 target.dispatchEvent(new Event('pagehide'));
 assert.deepEqual(events,[['loop',null],['dispose'],['release-context']]);
 release();target.dispatchEvent(new Event('pagehide'));
 assert.equal(events.length,3);
});

test('first draw waits for asynchronous shader preparation',async()=>{
 const {previewLifecycle}=await import('../../../devtools/asset_design/web/preview-lifecycle.mjs');
 const target=new EventTarget(),events=[];let finish;
 const ready=new Promise(resolve=>{finish=resolve;});
 const scene={},camera={};
 const renderer={compileAsync:async(s,c)=>{assert.equal(s,scene);assert.equal(c,camera);events.push('compile');await ready;},render:(s,c)=>{assert.equal(s,scene);assert.equal(c,camera);events.push('draw');},setAnimationLoop(){},dispose(){},forceContextLoss(){}};
 const lifecycle=previewLifecycle(renderer,target),pending=lifecycle.prepare(scene,camera);
 assert.deepEqual(events,['compile']);finish();
 assert.equal(await pending,true);assert.deepEqual(events,['compile','draw']);
});

test('leaving during shader preparation never draws into a released context',async()=>{
 const {previewLifecycle}=await import('../../../devtools/asset_design/web/preview-lifecycle.mjs');
 let finish,draws=0;
 const target=new EventTarget(),ready=new Promise(resolve=>{finish=resolve;});
 const renderer={compileAsync:()=>ready,render:()=>{draws++;},setAnimationLoop(){},dispose(){},forceContextLoss(){}};
 const lifecycle=previewLifecycle(renderer,target),pending=lifecycle.prepare({},{});
 target.dispatchEvent(new Event('pagehide'));finish();
 assert.equal(await pending,false);assert.equal(draws,0);
});

test('heavy previews can draw the first frame without waiting for shader preparation',async()=>{
 const target=new EventTarget(),events=[];
 const renderer={compileAsync:async()=>events.push('compile'),render:()=>events.push('draw'),setAnimationLoop(){},dispose(){},forceContextLoss(){}};
 const lifecycle=previewLifecycle(renderer,target),ready=await lifecycle.prepare({}, {}, {precompile:false});
 assert.equal(ready,true);assert.deepEqual(events,['draw']);
});

test('preview renderer retains antialiasing without changing scene lighting',async()=>{
 const {createPreviewRenderer}=await import('../../../devtools/asset_design/web/preview-lifecycle.mjs');
 const canvas={};let options;
 class Renderer{constructor(value){options=value;}}
 const renderer=createPreviewRenderer({WebGLRenderer:Renderer},canvas);
 assert.ok(renderer instanceof Renderer);
 assert.deepEqual(options,{canvas,antialias:true,alpha:false,powerPreference:'low-power',stencil:false});
 assert.equal(renderer.transmissionResolutionScale,1,'glass refraction retains full canvas resolution');
});

test('heavy previews can select a lower-cost high-performance context',async()=>{
 const {createPreviewRenderer}=await import('../../../devtools/asset_design/web/preview-lifecycle.mjs');
 let options;
 class Renderer{constructor(value){options=value;}}
 createPreviewRenderer({WebGLRenderer:Renderer},{},{antialias:false,powerPreference:'high-performance'});
 assert.deepEqual(options,{canvas:{},antialias:false,alpha:false,powerPreference:'high-performance',stencil:false});
});

test('a restored WebGL context requests a fresh draw, but never after release',()=>{
 const target=new EventTarget(),canvas=new EventTarget();let restored=0;
 const renderer={domElement:canvas,setAnimationLoop(){},dispose(){},forceContextLoss(){}};
 const lifecycle=previewLifecycle(renderer,target,{onRestore:()=>{restored++;}});
 canvas.dispatchEvent(new Event('webglcontextrestored'));assert.equal(restored,1);
 lifecycle.release();canvas.dispatchEvent(new Event('webglcontextrestored'));assert.equal(restored,1);
});
