// Explicit catalog associations own image meaning; model export names do not.
export function objectImages(catalog,object,version='') {
 const registered=new Set(catalog.assets.flatMap(a=>(a.files||[]).filter(f=>f.kind==='image').map(f=>f.path)));
 const family=object.startsWith('layout:terrace:')?'layout:terraces':object;
 const entries=new Map();
 for(const entry of catalog.imageReferences||[]){
  if(!registered.has(entry.path)||!entry.objects.some(id=>id===object||id===family))continue;
  const historical=entry.version&&entry.version!==version;
  entries.set(entry.path,{path:entry.path,name:entry.title+(entry.version?' · 来源 '+entry.version:''),
   kind:entry.kind==='reference'?'reference':historical?'history':entry.kind,
   shared:entry.objects.includes('layout:terraces')});
 }
 return [...entries.values()];
}
