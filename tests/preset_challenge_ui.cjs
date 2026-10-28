const fs=require('fs'),path=require('path'),assert=require('assert');
const {JSDOM}=require(process.env.UI_TEST_JSDOM||'jsdom');const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'control.html'),'utf8').replace(/<script[\s\S]*?<\/script>/g,'');
const dom=new JSDOM(html,{url:'http://127.0.0.1:8765/control.html',runScripts:'outside-only'}),w=dom.window;
let saves=0,selected=null;w.state={presets:{boards:[]},slotMachine:{patterns:[],event:{},queue:[],history:[]}};w.save=()=>saves++;w.persist=async()=>{};w.controlReady=true;w.renderSettings=()=>{};w.confirm=()=>true;w.openGiftPicker=input=>selected=input;w.giftCatalog=[{id:'5655',name:'Rose',imageUrl:'/rose.png'}];w.dirty=false;w.saving=false;w.timer=null;
w.fetch=async url=>({ok:true,json:async()=>url==='/api/network'?{baseUrl:'http://192.168.0.90:8765/'}:{slotMachine:{event:{},queue:[],history:[]}}});
w.eval(fs.readFileSync(path.join(root,'slot_controls.js'),'utf8'));
w.eval(fs.readFileSync(path.join(root,'presets_controls.js'),'utf8'));
const click=(scope,text)=>{const node=[...scope.querySelectorAll('button')].find(b=>b.textContent===text&&!b.disabled);assert(node,'button '+text);node.click();return node};
const set=(scope,label,value)=>{const node=[...scope.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent===label);assert(node,'field '+label);const input=node.querySelector('input,select,textarea');if(input.type==='checkbox'){input.checked=value;input.dispatchEvent(new w.Event('change',{bubbles:true}))}else{input.value=value;input.dispatchEvent(new w.Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}))}return input};
(async()=>{
 click(w.document,'＋ プリセットを追加');click(w.document,'＋ カードを追加');
 let board=w.state.presets.boards[0],card=w.document.querySelector('.presetEditor');
 click(card,'ギフト一覧から選択');assert(selected&&selected.classList.contains('presetGiftName'));
 selected.value='バラ';selected.dispatchEvent(new w.CustomEvent('input',{bubbles:true,detail:{giftId:'5655'}}));assert.equal(board.items[0].giftImageUrl,'/rose.png');assert.equal(board.items[0].giftId,'5655');
 set(card,'説明文','説明 <img src=x onerror=alert(1)>');set(card,'背景を完全透過',true);set(card,'フォント','meiryo');assert(board.transparent&&board.fontFamily==='meiryo');
 click(card,'＋ カードを追加');board.items[1].description='second';card=w.document.querySelector('.presetEditor');click(card,'↑');assert.equal(board.items[0].description,'second');
 const name=board.items[1].giftName;click(card,'CSSをリセット');assert.equal(board.items[1].giftName,name);
 card=w.document.querySelector('.presetEditor');assert.equal(card.querySelector('iframe').getAttribute('sandbox'),'allow-scripts');
 await new Promise(r=>setTimeout(r,100));assert(card.querySelector('[data-preset-path]').textContent.startsWith('http://192.168.0.90:8765/overlay_presets.html?id='));
 // The actual renderer uses textContent and never inserts description HTML.
 w.eval(fs.readFileSync(path.join(root,'preset_board.js'),'utf8'));const host=w.document.createElement('main'),style=w.document.createElement('style');w.renderPresetBoard(host,board,style);
 assert.equal(host.querySelectorAll('.presetCard').length,2);assert(host.textContent.includes('<img'));assert.equal(host.querySelectorAll('img').length,1);assert.equal(host.querySelector('img').loading,'lazy');assert.equal(host.style.getPropertyValue('--font'),'Meiryo,sans-serif');
 // Normal-only challenge controls expose an OFF default and all dedicated media settings.
 w.document.getElementById('addSlotPattern').click();await new Promise(r=>setTimeout(r,100));
 let slot=w.document.querySelector('.slotPattern');assert(slot);const toggle=[...slot.querySelectorAll('label')].find(x=>x.querySelector('span')?.textContent==='1G連チャレンジを使う');assert(toggle&&!toggle.querySelector('input').checked);
 set(slot,'1G連チャレンジを使う',true);set(slot,'1回のチャレンジ回転数','3');set(slot,'チャレンジ中の大当たり確率（1／○）','4');assert(w.state.slotMachine.patterns[0].challengeEnabled);assert.equal(w.state.slotMachine.patterns[0].challengeSpins,3);assert.equal(w.state.slotMachine.patterns[0].challengeHitDenominator,4);
 assert(slot.textContent.includes('チャレンジ中の大当たりの専用演出'));assert.equal([...slot.querySelectorAll('input[type=file]')].filter(n=>n.closest('details')?.textContent.includes('チャレンジ')).length>=6,true);
 set(slot,'筐体タイプ','at');slot=w.document.querySelector('.slotPattern');assert(!slot.textContent.includes('1G連チャレンジ（ノーマルタイプ専用）'));
 assert(saves>5);dom.window.close();
 console.log('PASS real DOM: presets tab/editor, gift catalog image selection, descriptions, themes/fonts/transparency, reorder, CSS isolation/reset, LAN URLs, normal-only challenge ON/OFF/probability/media controls');
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
