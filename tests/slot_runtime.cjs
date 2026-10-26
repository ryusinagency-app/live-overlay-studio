const fs=require('fs'),path=require('path');
const {JSDOM}=require(process.env.WIN_GACHA_TEST_JSDOM||'jsdom');
const root=path.resolve(__dirname,'..');
const overlay=fs.readFileSync(path.join(root,'overlay_slot.html'),'utf8');
for(const expected of ["releaseMedia(document.getElementById('monitorHost'),true)","releaseMedia(document.getElementById('cabinetHost'),true)","releaseMedia(bigEffectHost,true)"])
  if(!overlay.includes(expected))throw Error('slot shutdown does not release media: '+expected);
const html=fs.readFileSync(path.join(root,'control.html'),'utf8').replace(/<script[\s\S]*?<\/script>/g,'');
const dom=new JSDOM(html,{url:'http://127.0.0.1:8765/control.html',runScripts:'outside-only'});
const w=dom.window;w.confirm=()=>true;w.openGiftPicker=()=>{};w.save=()=>{};w.persist=async()=>{};
w.fetch=async url=>({ok:true,json:async()=>url==='/api/state'?w.state:{ok:true,slotMachine:w.state.slotMachine}});
w.state={slotMachine:{shortcutChoicePlus:'CTRL+ALT+6',shortcutChoiceMinus:'CTRL+ALT+SHIFT+6',queue:[],history:[],event:{active:false},patterns:[{id:'slot-1',name:'JUG',enabled:true,machineType:'at',giftName:'バラ',giftSpins:20,sign:'both',hitDenominator:199,replayEnabled:true,spinSeconds:1.8,stopInterval:.35,resultSeconds:1.2,hitNoticeSeconds:2,hitAlignSeconds:2.4,missSymbols:['BAR','7'],bigSymbolText:'7',bigWin:100,payouts:[{win:100,weight:100}],smallRoles:[{id:'grape',name:'ブドウ',enabled:true,probability:12,symbolText:'ブドウ',addSpinsEnabled:true,addSpins:3,addWinEnabled:false,win:0,audioVolume:75,freezeEnabled:true,freezeChance:10}],czEnabled:true,czEntryRate:10,czPatterns:[{id:'cz-1',name:'CZ 1',enabled:true,expectation:1,weight:20,atEntryRate:20,spinSeconds:1.8,stopInterval:.35,resultSeconds:1.2,seconds:3,animationUrl:'',audioUrl:'',audioVolume:75,videoVolume:70}],freezeEnabled:true,freezeDirectEnabled:true,freezeDenominator:8192,background:'#08090d',accent:'#ffcf59',textColor:'#ffffff',reelColor:'#f7f2df'}]}};
const controls=fs.readFileSync(path.join(root,'slot_controls.js'),'utf8');
for(const expected of ['AT中の回転時間（秒）','AT中のリール停止間隔（秒）','AT中の結果表示時間（秒）','AT中の大当たり演出時間（秒）','上位AT中の回転時間（秒）','上位AT中のリール停止間隔（秒）','上位AT中の結果表示時間（秒）','上位AT中の大当たり演出時間（秒）','AT中の追加ループ音源','上位AT中の追加ループ音源','フリーズ後の移行方法','上位AT突入演出を再生してから上位AT','突入演出を飛ばして上位AT中へ'])if(!controls.includes(expected))throw Error('missing '+expected);
w.eval(controls);
setTimeout(()=>{
  const card=w.document.querySelector('.slotPattern');
  if(!card)throw Error('slot pattern was not rendered');
  card.dataset.notReplaced='yes';
  const details=card.querySelector('details');if(details)details.open=true;
},100);
setTimeout(()=>{
  const card=w.document.querySelector('.slotPattern');
  if(card?.dataset.notReplaced!=='yes')throw Error('live polling replaced the settings editor');
  if(card.querySelector('details')&&!card.querySelector('details').open)throw Error('open settings were closed');
  const text=w.document.getElementById('slotSettings').textContent;
  for(const expected of ['筐体タイプ','大当たり確率','リプレイを使う','小役・リプレイ設定','成立時の演出時間（秒）','この小役でフリーズ抽選','フリーズ当選率','リール図柄一式','筐体画像サイズ','標準のGOGOランプを表示','GOGOランプの位置・サイズ','横位置（%）','縦位置（%）','表示幅（px）','表示高さ（px）','始動音（回転開始時・ループなし）','回転音（回転中ループ）','第一停止音','第二停止音','第三停止音','大当たり演出時間','大当たり演出の画像／動画','音源のみ','画像／動画＋音源','CZ設定','通常時のCZ突入率','CZ選択確率（重み）','CZ中のモニター画像／動画','CZ中の音源','AT突入率','結果表示（秒）','演出時間（秒）','AT中のモニター画像／動画','上位AT中のモニター画像／動画','上位AT突入画像／動画','上位AT突入音源','フリーズ・上位AT直行設定','直接フリーズ確率','フリーズ画像／動画','フリーズ音源','モニター表示テキスト','モニター文字色','モニター文字サイズ','±選択'])if(!text.includes(expected))throw Error('missing '+expected);
  if(w.document.querySelector('[data-category="slot"]')?.textContent!=='スロット')throw Error('slot tab missing');
  if(!w.document.querySelector('[data-view="slot"]'))throw Error('slot overlay link missing');
  console.log('PASS slot editor: independent tab, gift spins, odds, replay, small roles, AT and signed WIN controls');
  process.exit(0);
},1250);
