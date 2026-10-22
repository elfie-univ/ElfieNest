import test from 'node:test';
import assert from 'node:assert/strict';
import {readCatalog} from '../../../devtools/asset_design/web/catalog-request.mjs';

test('unchanged catalogue polling sends its validator and never parses an empty 304',async t=>{
 t.mock.method(globalThis,'fetch',async(url,options)=>{
  assert.equal(url,'/assets/design/catalog.json');
  assert.equal(options.headers['If-None-Match'],'"accepted"');
  return {status:304,ok:false,json(){throw Error('304 has no JSON');}};
 });
 assert.equal(await readCatalog('"accepted"'),null);
});

test('an unapplied publication can be requested again with the accepted validator',async t=>{
 const headers=[];
 t.mock.method(globalThis,'fetch',async(url,options)=>{
  headers.push(options.headers['If-None-Match']);
  return {status:200,ok:true,headers:{get:()=> '"pending"'},json:async()=>({assets:[{id:'new'}]})};
 });
 const first=await readCatalog('"accepted"');
 assert.equal(first.etag,'"pending"');
 // If its scene index is not ready, the controller keeps its old accepted tag.
 const retry=await readCatalog('"accepted"');
 assert.deepEqual(headers,['"accepted"','"accepted"']);
 assert.equal(retry.catalog.assets[0].id,'new');
});

test('failed requests reject without returning an accepted validator',async t=>{
 t.mock.method(globalThis,'fetch',async()=>({status:503,ok:false}));
 await assert.rejects(readCatalog('"accepted"'),/资产目录无法读取/);
});
