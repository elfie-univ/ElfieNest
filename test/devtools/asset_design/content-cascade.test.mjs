import {test} from 'node:test';
import assert from 'node:assert/strict';
import {designMenu,contentMenuTree} from '../../../devtools/asset_design/web/design-state.mjs';
test('two-level content menu lists furniture types directly under the furniture heading',()=>{
 const part=(id,label,count,order)=>({id,group:'kit',menuVisible:true,menuCategory:'plant',menuOrder:order,label,currentUsage:{count},versions:[{id:id+'v1'},{id:id+'v2'}]});
 const index={groups:{layout:'家具布置',kit:'家具'},objects:[{id:'layout:pod',group:'layout',label:'卧室',versions:[{id:'room'}]},part('part:tall','高杆橡皮树落地盆栽（4处引用）',4,1),part('part:short','矮杆橡皮树落地盆栽',4,2)]};
 const before=JSON.stringify(index),tree=contentMenuTree(designMenu(index,'part:tall'));
 assert.deepEqual(tree.map(x=>x.label),['家具布置','家具']);
 assert.equal(tree[0].section,true);assert.equal(tree[0].children[0].id,'layout:pod');assert.equal(tree[1].section,true);
 const furniture=tree[1];assert.deepEqual(furniture.children.map(x=>x.label),['植物']);
 assert.deepEqual(furniture.children[0].children.map(x=>[x.id,x.label]),[['part:tall','高杆橡皮树落地盆栽（4处引用）'],['part:short','矮杆橡皮树落地盆栽（4处引用）']]);
 assert.equal(JSON.stringify(index),before);
});

test('content cascade is the only visible classification control',async()=>{
 const {readFile}=await import('node:fs/promises');
 const html=await readFile(new URL('../../../devtools/asset_design/web/index.html',import.meta.url),'utf8');
 assert.match(html,/id="contentTrigger"[^>]*aria-haspopup="menu"/);
 assert.match(html,/id="contentMenu"/);
 assert.doesNotMatch(html,/id="furnitureType(?:Control)?"/);
 assert.match(html,/<select id="categorySelect"[^>]* hidden/);
});

test('chairs and stools have separate second-level choices',()=>{
 const entry=(id,menuCategory)=>({id,label:id,group:'kit',menuCategory,menuVisible:true,currentUsage:{count:2},versions:[{id:id+'v1'}]});
 const tree=contentMenuTree(designMenu({groups:{kit:'家具'},objects:[entry('part:chair','seating'),entry('part:pouf','stool')]},'part:chair'));
 assert.deepEqual(tree[0].children.map(x=>x.label),['椅子','坐墩']);
 assert.equal(tree[0].section,true);
});

async function cascadeFixture(){
 const {readFile}=await import('node:fs/promises'),{runInNewContext}=await import('node:vm');
 const source=await readFile(new URL('../../../devtools/asset_design/web/library.js',import.meta.url),'utf8');
 const events={},rect={left:430,bottom:100};let viewport=800;
 function element(tag){return {tag,children:[],style:{},attributes:{},hidden:false,
  append(child){child.parent=this;this.children.push(child);},replaceChildren(){this.children=[];},remove(){this.parent.children=this.parent.children.filter(c=>c!==this);},
  setAttribute(k,v){this.attributes[k]=v;},hasAttribute(k){return k in this.attributes;},focus(){},
  get firstElementChild(){return this.children[0];},get lastElementChild(){return this.children.at(-1);},
  querySelector(){return this.children.find(c=>c.tag==='button');},querySelectorAll(){return this.children.filter(c=>c.tag==='button');}
 };}
 const trigger=element('button'),popup=element('div');popup.hidden=true;trigger.getBoundingClientRect=()=>rect;
 popup.getBoundingClientRect=()=>({width:Math.min(viewport-24,popup.children.length*220+12)});
 const window={get innerWidth(){return viewport;},addEventListener(name,handler){events[name]=handler;}};
 const context={el:id=>id==='contentTrigger'?trigger:popup,window,document:{createElement:element,addEventListener(){}},contentMenuTree:()=>[{label:'家具',children:[{id:'chair',label:'椅子'}]}],confirmBusy:false,deleteBusy:false,catalogStale:false,chooseContent(){}};
 runInNewContext(source.slice(source.indexOf('function closeContentMenu()'),source.indexOf('function renderDesignPickers(')),context);
 context.renderContentCascade({},undefined);trigger.onclick();
 return {trigger,popup,rect,events,resize(width){viewport=width;events.resize();}};
}

test('content popup aligns to its trigger using the visible column width',async()=>{
 const {popup}=await cascadeFixture();
 assert.equal(popup.style.left,'430px');
 assert.equal(popup.style.top,'106px');
});

test('content popup only shifts for a wider submenu and realigns when it closes',async()=>{
 const {popup}=await cascadeFixture();
 popup.firstElementChild.firstElementChild.onclick();
 assert.equal(popup.style.left,'336px');
 popup.lastElementChild.firstElementChild.onkeydown({key:'ArrowLeft',preventDefault(){}});
 assert.equal(popup.style.left,'430px');
});

test('an open content popup follows scrolling and stays on screen after resize',async()=>{
 const {popup,rect,events,resize}=await cascadeFixture();
 rect.left=320;rect.bottom=70;events.scroll();
 assert.equal(popup.style.left,'320px');assert.equal(popup.style.top,'76px');
 resize(500);assert.equal(popup.style.left,'256px');
});
