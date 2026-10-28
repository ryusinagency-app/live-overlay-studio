const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node {
  constructor(tag='div'){this.tag=tag;this.children=[];this.style={setProperty(){}};this.classList={add(){},remove(){},toggle(){}}}
  append(...nodes){this.children.push(...nodes)}
  appendChild(node){this.append(node)}
  replaceChildren(...nodes){this.children=[...nodes]}
}
const nodes=new Map();
const context=vm.createContext({
 document:{getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)},
 createElement(tag){return new Node(tag)},documentElement:new Node()},
 requestAnimationFrame(){},setInterval(){},setTimeout(){return 1},clearTimeout(){},
 AbortController,fetch(){return new Promise(()=>{})},console
});
const html=fs.readFileSync('overlay_gift_history.html','utf8');
vm.runInContext([...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n'),context);
vm.runInContext(`
const testItems=Array.from({length:200},(_,id)=>({id,senderName:'sender'+id,giftName:'rose',count:1,avatarUrl:'/avatar'+id,giftImageUrl:'/gift'+id}));
for(const style of ['page','continuous','single','fade','slide','static']){
 config={columns:4,rows:2,direction:'vertical',style,speed:60,loop:true,delay:2000};
 draw(testItems);
 if(pageItems.flat().length!==200)throw Error('History entries were removed');
 const visited=new Set();
 for(let i=0;i<pages.length+1;i++){
  visited.add(index);
  const mountedCards=pages.reduce((count,page)=>count+page.children.length,0);
  const limit=style==='static'?8:style==='single'?3:24;
  if(mountedCards>limit)throw Error('Too many cards: '+mountedCards);
  if(!pages[index].children.length)throw Error('Visible page empty');
  if(style!=='static'){next=0;step()}
 }
 if(style!=='static'&&visited.size!==pages.length)throw Error('Not all history pages reachable');
}
config={columns:4,rows:2,direction:'horizontal',style:'page',speed:60,loop:false,delay:2000};draw(testItems);
for(let i=0;i<30;i++){next=0;step()}
if(index!==pages.length-1)throw Error('Non-looping history did not stay on last page');
`,context);
console.log('History: all 200 entries reachable; max 24 cards / 48 images (default layout); all six styles and non-loop end passed');
