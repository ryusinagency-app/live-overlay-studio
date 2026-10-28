const fs=require('fs'),path=require('path'),{JSDOM}=require(process.env.JSDOM_PATH||'/tmp/live-minecraft-ui-test/node_modules/jsdom');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8').replace('<script src="app.js"></script>','');
const state={version:'0.1.0',status:{rcon:'未接続',queuedCommands:0},game:{arena:{health:100,maxHealth:100,filled:0,capacity:27},multiplier:{active:false,multiplier:2,remainingSeconds:0,progress:0,threshold:5000}},config:{arena:{x:0,y:64,z:0,width:3,depth:3,height:3,frameBlock:'minecraft:obsidian',fillBlock:'minecraft:stone',maxHealth:100,holdSeconds:10,holdWin:1,clearAfterSuccess:true},commandDelayMs:35,multiplier:{threshold:5000,durationSeconds:300,multiplier:2,applyFill:true,applyTnt:true,applyWin:true},rcon:{host:'127.0.0.1',port:25575,password:''},winBridge:{enabled:false,url:'http://127.0.0.1:8765/api/minecraft-studio/win',token:''},effects:{one:{name:'埋める',kind:'fill',amount:1,win:0,description:'1個'}}}};
const dom=new JSDOM(html,{url:'http://127.0.0.1:8775/',runScripts:'outside-only',pretendToBeVisual:true});
const {window}=dom;window.structuredClone=global.structuredClone;window.HTMLDialogElement.prototype.showModal=function(){this.open=true};window.HTMLDialogElement.prototype.close=function(){this.open=false};
window.fetch=async(url,options={})=>({ok:true,json:async()=>url==='/api/gift-catalog'?{gifts:[{id:'rose',name:'Rose',price:1,imageUrl:'/rose.png'}]}:state});
window.setInterval=()=>0;window.setTimeout=()=>0;
window.eval(fs.readFileSync(path.join(root,'app.js'),'utf8'));
setImmediate(async()=>{
  const d=window.document;
  if(d.querySelectorAll('.effectCard').length!==1)throw Error('effect cards were not rendered');
  d.getElementById('addGiftEffect').click();await new Promise(r=>setImmediate(r));
  if(d.querySelectorAll('.giftChoice').length!==1)throw Error('gift catalog was not rendered');
  d.querySelector('.giftChoice').click();
  if(d.querySelectorAll('.effectCard').length!==2)throw Error('selected gift was not added');
  const countdown=d.getElementById('holdSeconds');if(countdown.value!=='10')throw Error('hold seconds not rendered');
  console.log('PASS UI tabs, settings, effect cards and gift catalog picker');
});
