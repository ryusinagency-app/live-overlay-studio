const assert=require('assert'),fs=require('fs'),vm=require('vm');
class Node{
 constructor(tag='div'){this.tag=tag;this.children=[];this.className='';this.dataset={};this.style={};this.disabled=false}
 append(...nodes){this.children.push(...nodes)}
 appendChild(node){this.append(node)}
 addEventListener(){}
 querySelectorAll(selector){
   const result=[];
   const matches=node=>selector==='button[data-choice]'?node.tag==='button'&&node.dataset.choice:
     selector.startsWith('.')?node.className.split(' ').includes(selector.slice(1)):false;
   const walk=node=>{for(const child of node.children){if(matches(child))result.push(child);walk(child)}};
   walk(this);return result;
 }
 querySelector(selector){return this.querySelectorAll(selector)[0]||null}
}
const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
const state={slotMachine:{patterns:[{id:'slot-1',name:'AT'},{id:'slot-2',name:'Normal'}],
 event:{id:1,active:true,patternId:'slot-1',appliedSpins:1,spinCount:10},
 choiceEvents:[{id:2,patternId:'slot-2',patternName:'Normal',senderName:'viewer',total:100,choiceReady:true}],
 queueCount:1}};
let posted=null,releaseChoice;
const context=vm.createContext({state,location:{origin:'http://localhost:8765',search:''},
 document:{head:new Node(),createElement:tag=>new Node(tag),getElementById:node,querySelectorAll:()=>[]},
 fetch:async(path,options)=>{
  if(path==='/api/network')return{json:async()=>({baseUrl:'http://localhost:8765/'})};
  if(path==='/api/slot/choose-sign'){
   posted=JSON.parse(options.body);
   await new Promise(resolve=>{releaseChoice=resolve});
   return{ok:true,json:async()=>({ok:true})};
  }
  if(path==='/api/slot/status')return{json:async()=>({slotMachine:{event:state.slotMachine.event,choiceEvents:[],queueCount:0}})};
  throw Error(path)
 },setInterval(){},setTimeout(){},clearTimeout(){},URL,URLSearchParams,AbortController,console});
let code=fs.readFileSync('slot_controls.js','utf8');
code=code.replace(/\}\)\(\);\s*$/,"globalThis.testChoices={renderSlotChoiceControls,updateLiveStatus,choose,waitingSlotChoices};})();");
vm.runInContext(code,context);
const api=context.testChoices,host=node('slotPatterns'),card1=new Node(),card2=new Node();
api.renderSlotChoiceControls(state.slotMachine.patterns[0],card1);
api.renderSlotChoiceControls(state.slotMachine.patterns[1],card2);
host.append(card1,card2);api.updateLiveStatus();
assert(card1.querySelectorAll('button[data-choice]').every(button=>button.disabled));
assert(card2.querySelectorAll('button[data-choice]').every(button=>!button.disabled));
const pending=api.choose('minus','slot-2');
assert.deepStrictEqual(posted,{eventId:2,choice:'minus'});
assert(card2.querySelectorAll('button[data-choice]').every(button=>button.disabled));
api.choose('plus','slot-2'); // duplicate click must not send another request
releaseChoice();
pending.then(()=>{
 assert.strictEqual(state.slotMachine.event.id,1);
 assert.strictEqual(state.slotMachine.event.appliedSpins,1);
 assert(card2.querySelectorAll('button[data-choice]').every(button=>button.disabled));
 assert(node('status').textContent.includes('－100WIN'));
 console.log('PASS: AT controls disabled; other machine selectable; correct eventId; duplicate click blocked; no full form redraw');
}).catch(error=>{console.error(error);process.exitCode=1});
