// Return the validator with its payload; callers accept both only after applying it.
export async function readCatalog(etag=''){
 const headers=etag?{'If-None-Match':etag}:{};
 const response=await fetch('/assets/design/catalog.json',{cache:'no-store',headers});
 if(response.status===304)return null;
 if(!response.ok)throw new Error('资产目录无法读取');
 return {catalog:await response.json(),etag:response.headers.get('ETag')||''};
}
