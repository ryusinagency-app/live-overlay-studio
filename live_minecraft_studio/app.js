const $=id=>document.getElementById(id);let current,workingEffects,workingGachas,giftCatalog=[],giftCatalogHandler=null,draggedEffectCard=null,dragPointerY=0,dragScrollFrame=0;
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(j.message||'通信エラー');return j}
function toast(message,error=false){const el=$('toast');el.textContent=message;el.className=error?'show error':'show';setTimeout(()=>el.className='',2600)}
function value(id){const el=$(id);return el.type==='number'?Number(el.value):el.type==='checkbox'?el.checked:el.value}
function set(id,v){const el=$(id);if(!el||el.dataset.dirty==='1')return;if(el.type==='checkbox')el.checked=!!v;else el.value=v??''}
function render(s){current=s;const c=s.config,a=s.game.arena,m=s.game.multiplier;
 $('connection').textContent=s.status.rcon;$('connection').className='badge '+(s.status.rcon==='接続中'?'ok':'');
 $('floorHealthCard').hidden=!a.floorEnabled;$('countdownState').textContent=a.defending?`残り ${a.holdRemainingSeconds}秒`:'埋め立て中';$('worldBridgeState').textContent=s.status.lastError||s.status.worldBridge||'';
 $('health').textContent=`${a.health} / ${a.maxHealth}`;$('healthBar').style.width=`${a.maxHealth?a.health/a.maxHealth*100:0}%`;
 $('filled').textContent=`${a.filled} / ${a.capacity}`;$('fillBar').style.width=`${a.capacity?a.filled/a.capacity*100:0}%`;
 $('feverState').textContent=m.enabled===false?'OFF':m.active?`${m.multiplier}倍タイム`:'通常';$('feverRemaining').textContent=m.enabled===false?'':m.active?`残り ${m.remainingSeconds}秒`:`次まで ${m.progress} / ${m.threshold}`;$('queued').textContent=s.status.queuedCommands;
 Object.entries(c.arena).forEach(([k,v])=>set(k,v));set('commandDelayMs',c.commandDelayMs);
 set('multiplierEnabled',c.multiplier.enabled!==false);set('waitingText',c.multiplier.waitingText||'次のフィーバーまで');set('threshold',c.multiplier.threshold);set('durationSeconds',c.multiplier.durationSeconds);set('multiplier',c.multiplier.multiplier);set('applyFill',c.multiplier.applyFill);set('applyTnt',c.multiplier.applyTnt);set('applyWin',c.multiplier.applyWin);['Repair','Items','Resize','Countdown','Player'].forEach(k=>set('apply'+k,c.multiplier['apply'+k]));set('stackingMode',c.multiplier.stackingMode);
 set('successText',c.overlay?.successText||'WIN！');set('rconHost',c.rcon.host);set('rconPort',c.rcon.port);if($('rconPassword').value==='')set('rconPassword',c.rcon.password);set('serverSoftware',c.rcon.serverSoftware||'未判定');$('serverVersionText').textContent=c.rcon.serverVersionText||'';set('winEnabled',c.winBridge.enabled);set('winUrl',c.winBridge.url);if($('winToken').value==='')set('winToken',c.winBridge.token);
 const es=c.overlay?.effectListStyle||{};set('effectColumns',es.columns??5);set('effectCardWidth',es.cardWidth??180);set('effectCardHeight',es.cardHeight??180);set('effectGap',es.gap??8);set('effectRadius',es.borderRadius??14);set('effectBackgroundColor',es.backgroundColor||'#61294f');set('effectBorderColor',es.borderColor||'#ef334e');set('effectTextColor',es.textColor||'#ffffff');set('effectAccentColor',es.accentColor||'#a4f4bf');set('effectGlowColor',es.feverGlowColor||'#ffd34e');set('effectNameFontSize',es.nameFontSize??18);set('effectAmountFontSize',es.effectFontSize??20);set('effectDescriptionFontSize',es.descriptionFontSize??13);set('effectImageSize',es.imageSize??74);
 const os=c.overlay?.arenaStyle||{},fs=c.overlay?.feverStyle||{};
 set('arenaOverlayWidth',os.width??620);set('arenaOverlayPadding',os.padding??18);set('arenaOverlayRadius',os.borderRadius??20);set('arenaOverlayOpacity',os.backgroundOpacity??88);set('arenaOverlayTitleSize',os.titleFontSize??26);set('arenaOverlayTextSize',os.textFontSize??16);set('arenaOverlayBackground',os.backgroundColor||'#080a0f');set('arenaOverlayBorder',os.borderColor||'#ef334e');set('arenaOverlayText',os.textColor||'#ffffff');set('arenaOverlayAccent',os.accentColor||'#35bc75');
 set('feverOverlayWidth',fs.width??600);set('feverOverlayPadding',fs.padding??22);set('feverOverlayRadius',fs.borderRadius??18);set('feverOverlayOpacity',fs.backgroundOpacity??91);set('feverOverlayTitleSize',fs.titleFontSize??40);set('feverOverlayTimerSize',fs.timerFontSize??42);set('feverOverlayTextSize',fs.textFontSize??22);set('feverOverlayBackground',fs.backgroundColor||'#111521');set('feverOverlayBorder',fs.borderColor||'#ffd34e');set('feverOverlayText',fs.textColor||'#ffffff');set('feverOverlayAccent',fs.accentColor||'#ffd34e');
 const gs=c.overlay?.gachaStyle||{};set('gachaOverlayWidth',gs.width??920);set('gachaOverlayPadding',gs.padding??24);set('gachaOverlayRadius',gs.borderRadius??24);set('gachaOverlayOpacity',gs.backgroundOpacity??96);set('gachaOverlayTitleSize',gs.titleFontSize??42);set('gachaOverlaySenderSize',gs.senderFontSize??25);set('gachaOverlayReelSize',gs.reelFontSize??34);set('gachaOverlayResultSize',gs.resultFontSize??34);set('gachaOverlayContinueSize',gs.continueFontSize??29);set('gachaOverlayBackground',gs.backgroundColor||'#1d0d28');set('gachaOverlayBorder',gs.borderColor||'#ef334e');set('gachaOverlayText',gs.textColor||'#ffffff');set('gachaOverlayAccent',gs.accentColor||'#ffd34e');
 const local=s.localServer||{},running=local.running===true,prepared=local.prepared===true;
 $('localServerState').textContent=running?'起動中':prepared?'準備済み・停止中':'初回準備が必要';
 $('localServerMessage').textContent=local.message||'';
 $('localServerLamp').className=running?'running':prepared?'prepared':'';
 $('javaStatus').textContent=local.java?.available?(local.java.version||'Java確認済み'):'Java 21は「サーバーを準備」で自動設定されます';
 $('prepareLocalServer').disabled=running;$('startLocalServer').disabled=!prepared||running;$('stopLocalServer').disabled=!running;
 $('specialStock').textContent=`全埋めボム ${a.bombCharges||0}回 ／ 連鎖ブロック ${a.chainCharges||0}回 ／ 現在の枠 ${a.actualWidth||a.width}×${a.actualDepth||a.depth}×${a.actualHeight||a.height} ／ 規定 ${a.holdSeconds}秒`;
 if(!workingEffects){workingEffects=structuredClone(c.effects);renderEffectCards()}
 if(!workingGachas){workingGachas=structuredClone(c.gachas||{});renderGachas()}
 renderSocial(c);
 document.querySelectorAll('.effectCard').forEach(card=>{const p=s.effectPreviews?.[card.dataset.id];if(p){card.classList.toggle('fever',p.feverApplied);card.querySelector('.effectiveAmount').textContent=p.effectiveLabel}});
}
const actionKindOptions=[['fill','指定個数を埋める'],['fill_layers','空きのある下段から指定段数を埋める'],['fill_percent','枠全体の指定割合分を追加で埋める'],['fill_all','全埋め'],['clear_all','全消し'],['tnt','TNT'],['repair','底の耐久回復'],['shield','シールド'],['bomb','全埋めボム補充'],['chain','連鎖ブロック補充'],['resize','枠サイズ変更'],['freeze','移動停止'],['launch','上へ吹き飛ばす'],['countdown','規定カウント変更'],['clear','指定個数を消去']];
const kindOptions=[...actionKindOptions,['gacha','スピナーガチャを回す']];
function gachaOptions(){const entries=Object.entries(workingGachas||current?.config?.gachas||{}).map(([id,g])=>[id,g.name||'スピナーガチャ']);return entries.length?entries:[['','先にガチャを追加してください']]}
function field(label,type,v,key,options){
 const wrap=document.createElement('label');wrap.textContent=label;
 const el=document.createElement(type==='select'?'select':'input');el.dataset.effectKey=key;el.className='effect'+key[0].toUpperCase()+key.slice(1);
 if(type==='select'){for(const [value,text] of options){const o=document.createElement('option');o.value=value;o.textContent=text;el.append(o)}el.value=v;}
 else {el.type=type;if(type==='checkbox'){el.checked=!!v;wrap.className='toggle'}else el.value=v??'';}
 wrap.append(el);return wrap;
}
function soundPicker(card,e){
 const wrap=document.createElement('div');wrap.className='soundPicker';
 const title=document.createElement('span');title.textContent='ギフト音源（20MBまで）';
 const current=document.createElement('small');current.className='soundFileName';current.textContent=e.soundFileName||(e.soundUrl?'設定済み':'未設定');
 const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.effectKey='soundUrl';hidden.value=e.soundUrl||'';
 const hiddenName=document.createElement('input');hiddenName.type='hidden';hiddenName.dataset.effectKey='soundFileName';hiddenName.value=e.soundFileName||'';
 const input=document.createElement('input');input.type='file';input.accept='audio/*,.mp3,.wav,.ogg,.m4a,.aac,.webm,.flac';
 const remove=document.createElement('button');remove.type='button';remove.textContent='音源を外す';remove.onclick=()=>{hidden.value='';hiddenName.value='';current.textContent='未設定';input.value='';hidden.dataset.dirty='1'};
 input.onchange=async()=>{const file=input.files?.[0];if(!file)return;if(file.size>20_000_000){toast('音声ファイルは20MB以内にしてください',true);input.value='';return}try{current.textContent='アップロード中…';const data=await new Promise((ok,ng)=>{const reader=new FileReader();reader.onload=()=>ok(String(reader.result).split(',')[1]||'');reader.onerror=ng;reader.readAsDataURL(file)});const r=await api('/api/sound-upload',{name:file.name,data});hidden.value=r.url;hiddenName.value=r.name;hidden.dataset.dirty='1';current.textContent=r.name;toast('音源を設定しました')}catch(err){current.textContent=hidden.value?(hiddenName.value||'設定済み'):'未設定';toast(err.message,true)}};
 wrap.append(title,current,input,remove,hidden,hiddenName);return wrap;
}
function effectTriggerPicker(id,e){
 const wrap=document.createElement('div');wrap.className='effectTriggerPicker';
 const title=document.createElement('strong');title.textContent='発動方法';
 const info=document.createElement('div');info.className='triggerGiftInfo';
 const img=document.createElement('img');img.src=e.giftImageUrl||'';img.alt='';img.hidden=!img.src;
 const text=document.createElement('span');text.textContent=e.giftName?`ギフト：${e.giftName}`:'ギフト：未設定';info.append(img,text);
 const choose=document.createElement('button');choose.type='button';choose.className='accent';choose.textContent=e.giftName?'発動ギフトを変更':'ギフト一覧から選択';
 choose.onclick=()=>{collectEffectCards();openGiftCatalog(gift=>{const item=workingEffects[id];item.giftId=String(gift.id||'');item.giftName=String(gift.name||'');item.giftImageUrl=String(gift.imageUrl||'');if(!Object.hasOwn(item,'imageMode'))item.imageMode='gift';$('giftDialog').close();renderEffectCards()})};
 const remove=document.createElement('button');remove.type='button';remove.textContent='ギフト発動を外す';remove.onclick=()=>{collectEffectCards();const item=workingEffects[id];item.giftId='';item.giftName='';item.giftImageUrl='';renderEffectCards()};
 wrap.append(title,info,choose,remove);return wrap;
}
function effectImagePicker(e){
 const wrap=document.createElement('div');wrap.className='effectImagePicker';
 const mode=field('効果一覧の画像','select',e.imageMode||'gift','imageMode',[['gift','発動ギフトの画像を使用'],['custom','任意の画像を使用'],['none','画像を表示しない']]);
 const preview=document.createElement('img');preview.className='effectImagePreview';preview.src=(e.imageMode==='custom'?e.customImageUrl:e.imageMode==='none'?'':e.giftImageUrl)||'';preview.alt='';preview.hidden=!preview.src;
 const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.effectKey='customImageUrl';hidden.value=e.customImageUrl||'';
 const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/gif,image/webp';
 const status=document.createElement('small');status.textContent=e.customImageUrl?'任意画像：設定済み':'任意画像：未設定';
 input.onchange=async()=>{const file=input.files?.[0];if(!file)return;if(file.size>5_000_000){toast('画像ファイルは5MB以内にしてください',true);input.value='';return}try{status.textContent='アップロード中…';const data=await new Promise((ok,ng)=>{const reader=new FileReader();reader.onload=()=>ok(String(reader.result).split(',')[1]||'');reader.onerror=ng;reader.readAsDataURL(file)});const r=await api('/api/image-upload',{name:file.name,data});hidden.value=r.url;hidden.dataset.dirty='1';mode.querySelector('select').value='custom';preview.src=r.url;preview.hidden=false;status.textContent=`任意画像：${r.name}`;toast('画像を設定しました')}catch(err){toast(err.message,true)}};
 const remove=document.createElement('button');remove.type='button';remove.textContent='任意画像を外す';remove.onclick=()=>{hidden.value='';hidden.dataset.dirty='1';input.value='';preview.src='';preview.hidden=true;status.textContent='任意画像：未設定'};
 mode.querySelector('select').onchange=()=>{const selected=mode.querySelector('select').value;preview.src=selected==='custom'?hidden.value:selected==='gift'?(e.giftImageUrl||''):'';preview.hidden=!preview.src};
 wrap.append(mode,preview,status,input,remove,hidden);return wrap;
}
function playEffectSound(effect){
 if(!effect?.soundEnabled||!effect.soundUrl)return;
 const audio=new Audio(effect.soundUrl);audio.volume=Math.max(0,Math.min(1,Number(effect.soundVolume??100)/100));audio.play().catch(()=>toast('音声を再生できませんでした',true));
 const seconds=Number(effect.soundSeconds||0);if(seconds>0)setTimeout(()=>{audio.pause();audio.currentTime=0},seconds*1000);
}
function collectEffectCards(){
 const result={};
 document.querySelectorAll('.effectCard').forEach(card=>{const e={...(workingEffects[card.dataset.id]||{})};
 card.querySelectorAll('[data-effect-key]').forEach(el=>e[el.dataset.effectKey]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value);
 e.additionalEffects=[...card.querySelectorAll('.additionalEffect')].map(editor=>{const action={};editor.querySelectorAll('[data-additional-key]').forEach(el=>action[el.dataset.additionalKey]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value);return action});
 if(!e.additionalEffects.length)delete e.additionalEffects;
 result[card.dataset.id]=e;});
 workingEffects=result;$('effectsJson').value=JSON.stringify(result,null,2);return result;
}
function renderEffectCards(){
 const host=$('effectCards');host.replaceChildren();
 for(const [id,e] of Object.entries(workingEffects||{})){
  const card=document.createElement('div');card.className='effectCard';card.dataset.id=id;
  card.draggable=true;
  const main=document.createElement('div');main.className='effectMain';
  const img=document.createElement('img');img.src=(e.imageMode==='custom'?e.customImageUrl:e.imageMode==='none'?'':e.giftImageUrl)||'';img.alt='';img.hidden=!img.src;
  const del=document.createElement('button');del.className='danger';del.textContent='削除';del.onclick=()=>{collectEffectCards();delete workingEffects[id];renderEffectCards()};
  const tryButton=document.createElement('button');tryButton.className='accent effectTestButton';tryButton.textContent='この効果をテスト';tryButton.onclick=()=>testConfigured(id);
  const drag=document.createElement('button');drag.type='button';drag.className='dragHandle';drag.textContent='↕ 移動';drag.title='ドラッグして並び替え';
  drag.onpointerdown=()=>card.dataset.dragReady='1';
  const up=document.createElement('button');up.type='button';up.textContent='↑';up.title='ひとつ上へ';up.onclick=()=>moveEffectCard(card,-1);
  const down=document.createElement('button');down.type='button';down.textContent='↓';down.title='ひとつ下へ';down.onclick=()=>moveEffectCard(card,1);
  const displayName=Object.hasOwn(e,'name')?e.name:(e.giftName||id);
  main.append(img,field('表示名（空欄なら表示しない）','text',displayName,'name'),field('効果','select',e.kind||'fill','kind',kindOptions),drag,up,down,tryButton,del);
  const amount=document.createElement('strong');amount.className='effectiveAmount';amount.textContent='保存後に反映';
  const settings=document.createElement('div');settings.className='form effectSettings';
  function add(label,type,key,fallback,kinds,options){const l=field(label,type,e[key]??fallback,key,options);if(kinds)l.dataset.kinds=kinds.join(',');settings.append(l);}
  add('この効果を有効にする','checkbox','enabled',true);
  settings.append(effectTriggerPicker(id,e));
  add('ギフト発動を許可するユーザーID（空欄は全員）','text','allowedGiftUserId','');
  add('数量・段数・割合（%）・補充回数','number','amount',1,['fill','fill_layers','fill_percent','tnt','repair','shield','bomb','chain','clear']);
  add('追加のWIN増減（通常は0）','number','win',0);
  add('TNTの種類','select','tntType','normal',['tnt'],[['normal','通常TNT'],['piercing','貫通TNT（縦一列）'],['timed','時限TNT'],['giant','巨大TNT（底ダメージ4倍）']]);
  add('時限TNT：爆発までの秒数','number','fuseSeconds',5,['tnt']);
  add('連鎖で広がる総ブロック数','number','spreadBlocks',27,['chain']);
  add('変更する方向','select','resizeAxis','both',['resize'],[['horizontal','横（幅・奥行）'],['height','高さ'],['both','横と高さの両方']]);
  add('サイズの増減（縮小はマイナス）','number','resizeDelta',1,['resize']);
  add('秒数（カウント短縮はマイナス）','number','seconds',5,['countdown','freeze']);
  add('規定カウントの変更方法','select','countdownMode','add',['countdown'],[['add','規定秒数へ加算・減算'],['set','規定秒数を指定値へ変更']]);
  add('上へ飛ばす強さ（0.1〜10）','number','strength',2,['launch']);
  add('回すガチャ','select','gachaId','',['gacha'],gachaOptions());
  add('ガチャの中身専用（通常ギフトでは発動しない）','checkbox','gachaOnly',false);
  add('新規フォローで発動','checkbox','followTriggerEnabled',false);
  add('個人いいねで発動','checkbox','individualLikeTriggerEnabled',false);
  add('個人いいね：何回ごと','number','individualLikeEvery',100);
  add('累計いいねで発動','checkbox','totalLikeTriggerEnabled',false);
  add('累計いいね：何回ごと','number','totalLikeEvery',1000);
  settings.append(effectImagePicker(e));
  add('このギフトにフィーバー倍率を適用','checkbox','useMultiplier',true);
  add('画面にメッセージを表示','checkbox','displayEnabled',true);
  add('ギフター名も表示','checkbox','showSender',true);
  add('メッセージの表示秒数','number','displaySeconds',4);
  add('表示文（空欄は効果量を自動表示）','text','displayText','');
  add('視聴者向け説明','text','description','');
  add('このギフトで音源を再生','checkbox','soundEnabled',false);
  add('音量（0〜100）','number','soundVolume',100);
  add('再生時間（秒、0で最後まで）','number','soundSeconds',0);
  settings.append(soundPicker(card,e));
  const additional=document.createElement('div');additional.className='additionalEffects';
  const additionalTitle=document.createElement('div');additionalTitle.className='sectionHead';
  const additionalHeading=document.createElement('h3');additionalHeading.textContent='このギフトで同時に発動する効果';
  const addEffect=document.createElement('button');addEffect.type='button';addEffect.className='addEffectButton';addEffect.textContent='＋ 効果を追加';addEffect.onclick=()=>{collectEffectCards();const item=workingEffects[id];item.additionalEffects=[...(item.additionalEffects||[]),{kind:'fill',amount:1,win:0,useMultiplier:true}];renderEffectCards()};
  additionalTitle.append(additionalHeading,addEffect);additional.append(additionalTitle);
  (e.additionalEffects||[]).forEach((action,index)=>additional.append(renderAdditionalEffect(id,action,index)));
  const design=document.createElement('details');design.className='cardDesign';
  const designTitle=document.createElement('summary');designTitle.textContent='このカードの見た目・表示設定';
  const designFields=document.createElement('div');designFields.className='form effectSettings';
  function designAdd(label,type,key,fallback){designFields.append(field(label,type,e[key]??fallback,key));}
  designAdd('効果一覧に表示','checkbox','overlayVisible',true);
  designAdd('このカードだけ個別デザイン','checkbox','useCustomStyle',false);
  designAdd('背景色','color','cardBackgroundColor','#61294f');
  designAdd('枠線色','color','cardBorderColor','#ef334e');
  designAdd('文字色','color','cardTextColor','#ffffff');
  designAdd('効果量の色','color','cardAccentColor','#a4f4bf');
  designAdd('フィーバー中の発光色','color','cardGlowColor','#ffd34e');
  designAdd('カード幅','number','cardWidth',180);
  designAdd('カード高さ','number','cardHeight',180);
  designAdd('ギフト名の文字サイズ','number','nameFontSize',18);
  designAdd('効果量の文字サイズ','number','effectFontSize',20);
  designAdd('説明の文字サイズ','number','descriptionFontSize',13);
  designAdd('画像サイズ','number','imageSize',74);
  design.append(designTitle,designFields);
  const hint=document.createElement('p');hint.className='note';hint.textContent='表示名は空欄にできます。主効果と追加効果の表示はこのカードの「表示文」1か所で編集します。{amount}＝最初の効果量、{effects}＝すべての確定効果、{seconds}＝秒数、{strength}＝強さ、{name}＝ギフター名、{gift}＝発動ギフト名を使用できます。';
  const kind=main.querySelector('select');const visibility=()=>settings.querySelectorAll('[data-kinds]').forEach(l=>l.hidden=!l.dataset.kinds.split(',').includes(kind.value));kind.onchange=visibility;visibility();
  card.append(main,amount,settings,additional,design,hint);host.append(card);
 }
 enableEffectDrag();
 $('effectsJson').value=JSON.stringify(workingEffects,null,2);
}
function renderAdditionalEffect(cardId,action,index){
 const editor=document.createElement('details');editor.className='additionalEffect';editor.open=true;
 const summary=document.createElement('summary');summary.textContent=`追加効果 ${index+1}`;
 const fields=document.createElement('div');fields.className='form effectSettings';
 function add(label,type,key,fallback,kinds,options){const wrap=field(label,type,action[key]??fallback,key,options);const el=wrap.querySelector('[data-effect-key]');delete el.dataset.effectKey;el.dataset.additionalKey=key;if(kinds)wrap.dataset.kinds=kinds.join(',');fields.append(wrap)}
 add('効果','select','kind','fill',null,actionKindOptions);
 add('数量・段数・割合（%）・補充回数','number','amount',1,['fill','fill_layers','fill_percent','tnt','repair','shield','bomb','chain','clear']);
 add('WIN増減','number','win',0);
 add('TNTの種類','select','tntType','normal',['tnt'],[['normal','通常TNT'],['piercing','貫通TNT'],['timed','時限TNT'],['giant','巨大TNT']]);
 add('時限TNT：爆発までの秒数','number','fuseSeconds',5,['tnt']);
 add('連鎖で広がる総ブロック数','number','spreadBlocks',27,['chain']);
 add('変更する方向','select','resizeAxis','both',['resize'],[['horizontal','横'],['height','高さ'],['both','横と高さ']]);
 add('サイズの増減','number','resizeDelta',1,['resize']);
 add('秒数','number','seconds',5,['countdown','freeze']);
 add('規定カウントの変更方法','select','countdownMode','add',['countdown'],[['add','加算・減算'],['set','指定値へ変更']]);
 add('上へ飛ばす強さ','number','strength',2,['launch']);
 add('フィーバー倍率を適用','checkbox','useMultiplier',true);
 const remove=document.createElement('button');remove.type='button';remove.className='danger';remove.textContent='この追加効果を削除';remove.onclick=()=>{collectEffectCards();workingEffects[cardId].additionalEffects.splice(index,1);renderEffectCards()};fields.append(remove);
 const kind=fields.querySelector('[data-additional-key="kind"]');const visibility=()=>fields.querySelectorAll('[data-kinds]').forEach(w=>w.hidden=!w.dataset.kinds.split(',').includes(kind.value));kind.onchange=visibility;visibility();
 editor.append(summary,fields);return editor;
}
function moveEffectCard(card,direction){const sibling=direction<0?card.previousElementSibling:card.nextElementSibling;if(!sibling)return;if(direction<0)card.parentElement.insertBefore(card,sibling);else card.parentElement.insertBefore(sibling,card);collectEffectCards()}
function dragAutoScroll(){if(!draggedEffectCard){dragScrollFrame=0;return}const edge=Math.min(160,window.innerHeight*.22);let speed=0;if(dragPointerY<edge)speed=-Math.ceil((edge-dragPointerY)/edge*24);else if(dragPointerY>window.innerHeight-edge)speed=Math.ceil((dragPointerY-(window.innerHeight-edge))/edge*24);if(speed)window.scrollBy(0,speed);dragScrollFrame=requestAnimationFrame(dragAutoScroll)}
document.addEventListener('dragover',e=>{if(!draggedEffectCard)return;e.preventDefault();dragPointerY=e.clientY;if(!dragScrollFrame)dragScrollFrame=requestAnimationFrame(dragAutoScroll)});
function enableEffectDrag(){document.querySelectorAll('.effectCard').forEach(card=>{card.ondragstart=e=>{if(card.dataset.dragReady!=='1'){e.preventDefault();return}draggedEffectCard=card;dragPointerY=e.clientY;card.classList.add('dragging');e.dataTransfer.effectAllowed='move';if(!dragScrollFrame)dragScrollFrame=requestAnimationFrame(dragAutoScroll)};card.ondragend=()=>{delete card.dataset.dragReady;card.classList.remove('dragging');draggedEffectCard=null;if(dragScrollFrame)cancelAnimationFrame(dragScrollFrame);dragScrollFrame=0;collectEffectCards()};card.ondragover=e=>{if(!draggedEffectCard||draggedEffectCard===card)return;e.preventDefault();const box=card.getBoundingClientRect();card.parentElement.insertBefore(draggedEffectCard,e.clientY<box.top+box.height/2?card:card.nextElementSibling)}})}
function effectListStyle(){return {columns:value('effectColumns'),cardWidth:value('effectCardWidth'),cardHeight:value('effectCardHeight'),gap:value('effectGap'),borderRadius:value('effectRadius'),backgroundColor:value('effectBackgroundColor'),borderColor:value('effectBorderColor'),textColor:value('effectTextColor'),accentColor:value('effectAccentColor'),feverGlowColor:value('effectGlowColor'),nameFontSize:value('effectNameFontSize'),effectFontSize:value('effectAmountFontSize'),descriptionFontSize:value('effectDescriptionFontSize'),imageSize:value('effectImageSize')}}
function overlayStyles(){return {arenaStyle:{width:value('arenaOverlayWidth'),padding:value('arenaOverlayPadding'),borderRadius:value('arenaOverlayRadius'),backgroundOpacity:value('arenaOverlayOpacity'),titleFontSize:value('arenaOverlayTitleSize'),textFontSize:value('arenaOverlayTextSize'),backgroundColor:value('arenaOverlayBackground'),borderColor:value('arenaOverlayBorder'),textColor:value('arenaOverlayText'),accentColor:value('arenaOverlayAccent')},feverStyle:{width:value('feverOverlayWidth'),padding:value('feverOverlayPadding'),borderRadius:value('feverOverlayRadius'),backgroundOpacity:value('feverOverlayOpacity'),titleFontSize:value('feverOverlayTitleSize'),timerFontSize:value('feverOverlayTimerSize'),textFontSize:value('feverOverlayTextSize'),backgroundColor:value('feverOverlayBackground'),borderColor:value('feverOverlayBorder'),textColor:value('feverOverlayText'),accentColor:value('feverOverlayAccent')},gachaStyle:{width:value('gachaOverlayWidth'),padding:value('gachaOverlayPadding'),borderRadius:value('gachaOverlayRadius'),backgroundOpacity:value('gachaOverlayOpacity'),titleFontSize:value('gachaOverlayTitleSize'),senderFontSize:value('gachaOverlaySenderSize'),reelFontSize:value('gachaOverlayReelSize'),resultFontSize:value('gachaOverlayResultSize'),continueFontSize:value('gachaOverlayContinueSize'),backgroundColor:value('gachaOverlayBackground'),borderColor:value('gachaOverlayBorder'),textColor:value('gachaOverlayText'),accentColor:value('gachaOverlayAccent')}}}
function gfield(label,type,v,key,options){const wrap=document.createElement('label');wrap.textContent=label;const el=document.createElement(type==='select'?'select':'input');el.dataset.gachaKey=key;if(type==='select'){for(const [value,text] of options||[]){const o=document.createElement('option');o.value=value;o.textContent=text;el.append(o)}el.value=v??''}else{el.type=type;if(type==='checkbox'){el.checked=!!v;wrap.className='toggle'}else el.value=v??''}wrap.append(el);return wrap}
function effectOptions(){return Object.entries(workingEffects||{}).filter(([,e])=>e.kind!=='gacha').map(([id,e])=>[id,e.name||e.giftName||id])}
function gachaSoundPicker(g,key,label,volumeKey,secondsKey){const wrap=document.createElement('div');wrap.className='soundPicker';const title=document.createElement('span');title.textContent=label;const status=document.createElement('small');status.textContent=g[key]?'設定済み':'未設定';const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.gachaKey=key;hidden.value=g[key]||'';const input=document.createElement('input');input.type='file';input.accept='audio/*,.mp3,.wav,.ogg,.m4a,.aac,.webm,.flac';const volume=document.createElement('input');volume.type='number';volume.min='0';volume.max='100';volume.value=g[volumeKey]??g.soundVolume??100;volume.dataset.gachaKey=volumeKey;volume.title='音量（0〜100）';const seconds=document.createElement('input');seconds.type='number';seconds.min='0';seconds.max='600';seconds.step='.1';seconds.value=g[secondsKey]??0;seconds.dataset.gachaKey=secondsKey;seconds.title='再生時間（秒、0で演出に合わせる）';const volumeLabel=document.createElement('label');volumeLabel.textContent='音量（0〜100）';volumeLabel.append(volume);const secondsLabel=document.createElement('label');secondsLabel.textContent='再生時間（秒、0で演出に合わせる）';secondsLabel.append(seconds);const remove=document.createElement('button');remove.type='button';remove.textContent='音源を外す';remove.onclick=()=>{hidden.value='';status.textContent='未設定';input.value=''};input.onchange=async()=>{const file=input.files?.[0];if(!file)return;if(file.size>20_000_000){toast('音声ファイルは20MB以内にしてください',true);return}try{status.textContent='アップロード中…';const data=await new Promise((ok,ng)=>{const reader=new FileReader();reader.onload=()=>ok(String(reader.result).split(',')[1]||'');reader.onerror=ng;reader.readAsDataURL(file)});const r=await api('/api/sound-upload',{name:file.name,data});hidden.value=r.url;status.textContent=file.name;toast('音源を設定しました')}catch(err){toast(err.message,true)}};wrap.append(title,status,input,remove,volumeLabel,secondsLabel,hidden);return wrap}
function gachaTriggerPicker(id,g){const wrap=document.createElement('div');wrap.className='gachaTriggerPicker';const info=document.createElement('div');const img=document.createElement('img');img.src=g.triggerGiftImageUrl||'';img.alt='';const text=document.createElement('span');text.textContent=g.triggerGiftName?`発動ギフト：${g.triggerGiftName}`:'発動ギフト：未設定';info.append(img,text);const choose=document.createElement('button');choose.type='button';choose.className='accent';choose.textContent='ギフト一覧から発動ギフトを選択';choose.onclick=()=>{collectGachas();openGiftCatalog(gift=>{workingGachas[id].triggerGiftId=String(gift.id||'');workingGachas[id].triggerGiftName=String(gift.name||'');workingGachas[id].triggerGiftImageUrl=String(gift.imageUrl||'');$('giftDialog').close();renderGachas()})};const remove=document.createElement('button');remove.type='button';remove.textContent='発動ギフトを外す';remove.onclick=()=>{collectGachas();workingGachas[id].triggerGiftId='';workingGachas[id].triggerGiftName='';workingGachas[id].triggerGiftImageUrl='';renderGachas()};wrap.append(info,choose,remove);return wrap}
function gachaReactionSettings(g){const wrap=document.createElement('div');wrap.className='gachaReactionSettings';wrap.append(gfield('新規フォローで発動','checkbox',g.followTriggerEnabled===true,'followTriggerEnabled'),gfield('個人いいねで発動','checkbox',g.individualLikeTriggerEnabled===true,'individualLikeTriggerEnabled'),gfield('個人いいね：何回ごと','number',g.individualLikeEvery??100,'individualLikeEvery'),gfield('累計いいねで発動','checkbox',g.totalLikeTriggerEnabled===true,'totalLikeTriggerEnabled'),gfield('累計いいね：何回ごと','number',g.totalLikeEvery??1000,'totalLikeEvery'));return wrap}
function collectGachas(){const result={};document.querySelectorAll('.gachaCard').forEach(card=>{const g={...(workingGachas[card.dataset.id]||{})};card.querySelectorAll('[data-gacha-key]').forEach(el=>g[el.dataset.gachaKey]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value);g.entries=[...card.querySelectorAll('.gachaEntry')].map(row=>{const entry={};row.querySelectorAll('[data-entry-key]').forEach(el=>entry[el.dataset.entryKey]=el.type==='number'?Number(el.value):el.value);return entry});result[card.dataset.id]=g});workingGachas=result;return result}
function renderGachas(){const host=$('gachaCards');host.replaceChildren();for(const [id,g] of Object.entries(workingGachas||{})){const card=document.createElement('div');card.className='gachaCard';card.dataset.id=id;const head=document.createElement('div');head.className='sectionHead';const title=document.createElement('h3');title.textContent=g.name||'スピナーガチャ';const test=document.createElement('button');test.className='accent';test.textContent='このガチャをテスト';test.onclick=()=>testGacha(id);const del=document.createElement('button');del.className='danger';del.textContent='削除';del.onclick=()=>{collectGachas();delete workingGachas[id];renderGachas()};head.append(title,test,del);
const form=document.createElement('div');form.className='form effectSettings';form.append(gfield('ガチャ名','text',g.name||'スピナーガチャ','name'),gfield('使用する','checkbox',g.enabled!==false,'enabled'),gfield('効果一覧に表示','checkbox',g.showInEffectList!==false,'showInEffectList'),gfield('回転時間（秒）','number',g.spinSeconds??5,'spinSeconds'),gfield('継続システム','checkbox',g.continueEnabled===true,'continueEnabled'),gfield('継続率（%）','number',g.continueRate??70,'continueRate'),gfield('最大継続回数','number',g.maxSpins??20,'maxSpins'),gfield('継続時の次回転まで（秒）','number',g.continueDelaySeconds??2,'continueDelaySeconds'));
form.append(gachaSoundPicker(g,'giftSoundUrl','ギフトを受けた時の音源','giftSoundVolume','giftSoundSeconds'),gachaSoundPicker(g,'spinSoundUrl','回転中のリール音','spinSoundVolume','spinSoundSeconds'),gachaSoundPicker(g,'resultSoundUrl','結果決定音','resultSoundVolume','resultSoundSeconds'));
form.prepend(gachaTriggerPicker(id,g));
form.prepend(gachaReactionSettings(g));
const entries=document.createElement('div');entries.className='gachaEntries';const entryHead=document.createElement('div');entryHead.className='sectionHead';const h=document.createElement('h4');h.textContent='ガチャの中身と確率';const add=document.createElement('button');add.textContent='＋ 中身を追加';add.onclick=()=>{collectGachas();const options=effectOptions();if(!options.length){toast('先にギフト効果を追加してください',true);return}workingGachas[id].entries.push({effectId:options[0][0],weight:1,label:''});renderGachas()};entryHead.append(h,add);entries.append(entryHead);const total=(g.entries||[]).reduce((n,e)=>n+Math.max(0,Number(e.weight)||0),0)||1;(g.entries||[]).forEach((entry,index)=>entries.append(renderGachaEntry(id,entry,index,total)));card.append(head,form,entries);host.append(card)}}
function renderGachaEntry(gachaId,entry,index,total){const row=document.createElement('div');row.className='gachaEntry';function ef(label,type,key,val,options){const wrap=document.createElement('label');wrap.textContent=label;const el=document.createElement(type==='select'?'select':'input');el.dataset.entryKey=key;if(type==='select'){for(const [v,t] of options){const o=document.createElement('option');o.value=v;o.textContent=t;el.append(o)}el.value=val}else{el.type=type;el.value=val??''}wrap.append(el);row.append(wrap)}ef('発動する効果','select','effectId',entry.effectId,effectOptions());ef('表示名（空欄は効果名）','text','label',entry.label||'');ef('確率の重み','number','weight',entry.weight??1);const percent=document.createElement('strong');percent.textContent=`${(Math.max(0,Number(entry.weight)||0)/total*100).toFixed(1)}%`;const remove=document.createElement('button');remove.className='danger';remove.textContent='削除';remove.onclick=()=>{collectGachas();workingGachas[gachaId].entries.splice(index,1);renderGachas()};row.append(percent,remove);return row}
function targetOptions(){return [['','選択してください'],...Object.entries(workingEffects||{}).map(([id,e])=>['effect:'+id,'効果：'+(e.name||id)]),...Object.entries(workingGachas||{}).map(([id,g])=>['gacha:'+id,'ガチャ：'+(g.name||id)])]}
function setTargetSelect(id,target){const el=$(id);if(el.dataset.dirty==='1')return;el.replaceChildren(...targetOptions().map(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;return o}));el.value=target||''}
function renderSocial(c){const runtime=c.socialRuntime||{};$('socialStats').textContent=`記録済み新規フォロー ${runtime.followedUsers?.length||0}人 ／ 累計いいね ${runtime.totalLikes||0}回`}
async function testGacha(id){collectGachas();try{await api('/api/config',{gachas:workingGachas});const r=await api('/api/test-gacha',{gachaId:id});toast(r.message);refresh()}catch(e){toast(e.message,true)}}
function addBlankEffect(){collectEffectCards();const id='effect-'+Date.now();workingEffects[id]={name:'',kind:'fill',amount:1,win:0,enabled:true,giftId:'',giftName:'',giftImageUrl:'',imageMode:'none',allowedGiftUserId:'',displayText:'',description:'',overlayVisible:true,useMultiplier:true};renderEffectCards();setTimeout(()=>document.querySelector(`.effectCard[data-id="${id}"]`)?.scrollIntoView({behavior:'smooth',block:'center'}),0)}
function renderGiftCatalog(){const q=$('giftSearch').value.trim().toLowerCase();$('giftCatalog').replaceChildren(...giftCatalog.filter(g=>!q||String(g.name).toLowerCase().includes(q)||String(g.price).includes(q)).map(g=>{const b=document.createElement('button');b.className='giftChoice';const img=document.createElement('img');img.src=g.imageUrl||'';const n=document.createElement('b');n.textContent=g.name||'ギフト';const p=document.createElement('small');p.textContent=`${g.price||0}コイン`;b.append(img,n,p);b.onclick=()=>giftCatalogHandler?.(g);return b}))}
async function refresh(){try{render(await api('/api/state'))}catch(e){$('connection').textContent='停止';}}
async function save(body,message='保存しました'){try{const r=await api('/api/config',body);document.querySelectorAll('[data-dirty="1"]').forEach(el=>delete el.dataset.dirty);render(r.state);toast(message)}catch(e){toast(e.message,true)}}
async function test(id){try{const r=await api('/api/test-effect',{giftId:id,coins:0});toast(r.message||'テストを開始しました');refresh()}catch(e){toast(e.message,true)}}
async function testConfigured(id){collectEffectCards();try{const effect=workingEffects[id];const saved=await api('/api/config',{effects:workingEffects});document.querySelectorAll('[data-dirty="1"]').forEach(el=>delete el.dataset.dirty);render(saved.state);const r=await api('/api/test-effect',{giftId:id,coins:0});playEffectSound(effect);toast(r.message||'テストを開始しました');refresh()}catch(e){toast(e.message,true)}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('[data-page]').forEach(p=>p.hidden=p.dataset.page!==b.dataset.tab)});
document.addEventListener('input',event=>{if(event.target.matches('input,select,textarea'))event.target.dataset.dirty='1'});
document.addEventListener('change',event=>{if(event.target.matches('input,select,textarea'))event.target.dataset.dirty='1'});
$('saveArena').onclick=()=>save({arena:{x:value('x'),y:value('y'),z:value('z'),width:value('width'),depth:value('depth'),height:value('height'),frameBlock:value('frameBlock'),fillBlock:value('fillBlock'),minWidth:value('minWidth'),maxWidth:value('maxWidth'),minHeight:value('minHeight'),maxHeight:value('maxHeight'),maxHealth:value('maxHealth'),floorEnabled:value('floorEnabled'),floorDamage:value('floorDamage'),floorPenalty:value('floorPenalty'),holdSeconds:value('holdSeconds'),holdWin:value('holdWin'),clearAfterSuccess:value('clearAfterSuccess'),daylightFixed:value('daylightFixed'),clearWeather:value('clearWeather')},overlay:{successText:value('successText')},commandDelayMs:value('commandDelayMs')});
$('buildArena').onclick=async()=>{try{const r=await api('/api/arena/build',{});toast('天井なしの保護された枠を生成しています')}catch(e){toast(e.message,true)}};
$('saveEffects').onclick=async()=>{collectEffectCards();await save({effects:workingEffects});workingEffects=undefined};
$('saveEffectDesign').onclick=()=>save({overlay:{effectListStyle:effectListStyle()}},'一括デザインを保存しました');
$('saveOverlayDesign').onclick=()=>save({overlay:overlayStyles()},'オーバーレイのデザインを保存しました');
$('resetCardStyles').onclick=async()=>{collectEffectCards();Object.values(workingEffects).forEach(e=>e.useCustomStyle=false);renderEffectCards();await save({effects:workingEffects,overlay:{effectListStyle:effectListStyle()}},'全カードを一括デザインへ揃えました');workingEffects=undefined};
$('applyEffectsJson').onclick=()=>{try{workingEffects=JSON.parse($('effectsJson').value);renderEffectCards();toast('JSONを画面へ反映しました')}catch(e){toast('JSONの形式を確認してください',true)}};
async function openGiftCatalog(handler){try{giftCatalogHandler=handler;const r=await api('/api/gift-catalog');giftCatalog=r.gifts||[];renderGiftCatalog();$('giftDialog').showModal()}catch(e){toast(e.message,true)}}
$('addGiftEffect').onclick=addBlankEffect;$('addGiftEffectBottom').onclick=addBlankEffect;
$('closeGiftDialog').onclick=()=>$('giftDialog').close();$('giftSearch').oninput=renderGiftCatalog;
$('addGacha').onclick=()=>{collectGachas();const id='gacha-'+Date.now();workingGachas[id]={name:'新しいスピナーガチャ',enabled:true,showInEffectList:true,spinSeconds:5,continueEnabled:false,continueRate:70,maxSpins:20,continueDelaySeconds:2,giftSoundVolume:100,giftSoundSeconds:0,spinSoundVolume:100,spinSoundSeconds:0,resultSoundVolume:100,resultSoundSeconds:0,entries:[]};renderGachas();collectEffectCards();renderEffectCards()};
$('saveGachas').onclick=async()=>{collectGachas();await save({gachas:workingGachas},'ガチャ設定を保存しました');workingGachas=undefined};
$('resetSocial').onclick=async()=>{if(!confirm('新規フォロー判定といいね回数をすべてリセットしますか？'))return;try{const r=await api('/api/reset-social',{});render(r.state);toast(r.message)}catch(e){toast(e.message,true)}};
$('resetAll').onclick=async()=>{if(!confirm('倍率タイムのコイン数・耐久値・埋め立て状況・枠サイズをすべて初期状態へ戻しますか？'))return;try{const r=await api('/api/reset-all',{});render(r.state);toast(r.message)}catch(e){toast(e.message,true)}};
$('saveFever').onclick=()=>save({multiplier:{enabled:value('multiplierEnabled'),waitingText:value('waitingText'),threshold:value('threshold'),durationSeconds:value('durationSeconds'),multiplier:value('multiplier'),applyFill:value('applyFill'),applyTnt:value('applyTnt'),applyWin:value('applyWin'),applyRepair:value('applyRepair'),applyItems:value('applyItems'),applyResize:value('applyResize'),applyCountdown:value('applyCountdown'),applyPlayer:value('applyPlayer'),stackingMode:value('stackingMode')}});
async function localServerAction(path,body,message){const buttons=['prepareLocalServer','startLocalServer','stopLocalServer'].map($);buttons.forEach(b=>b.disabled=true);toast(message);try{const r=await api(path,body||{});render(r.state);toast(r.message||'完了しました')}catch(e){toast(e.message,true)}finally{setTimeout(refresh,400)}}
$('prepareLocalServer').onclick=()=>localServerAction('/api/local-server/prepare',{eulaAccepted:value('eulaAccepted')},'サーバーを準備しています');
$('startLocalServer').onclick=()=>localServerAction('/api/local-server/start',{},'Minecraftサーバーを起動しています');
$('stopLocalServer').onclick=()=>localServerAction('/api/local-server/stop',{},'ワールドを保存して停止しています');
$('saveConnection').onclick=()=>save({rcon:{host:value('rconHost'),port:value('rconPort'),password:value('rconPassword')}});
$('testConnection').onclick=async()=>{try{const r=await api('/api/rcon/test',{});toast(r.message||'接続できました');refresh()}catch(e){toast(e.message,true)}};
$('detectServer').onclick=async()=>{try{await save({rcon:{host:value('rconHost'),port:value('rconPort'),password:value('rconPassword')}},'接続設定を保存しました');const r=await api('/api/rcon/detect',{});set('serverSoftware',r.software);$('serverVersionText').textContent=r.detail||'';toast(`${r.software} と判定しました`)}catch(e){toast(e.message,true)}};
$('saveWin').onclick=()=>save({winBridge:{enabled:value('winEnabled'),url:value('winUrl'),token:value('winToken')}});
document.querySelectorAll('[data-copy-url]').forEach(button=>button.onclick=async()=>{const url=button.parentElement.querySelector('code')?.textContent?.trim()||'';try{await navigator.clipboard.writeText(url);toast('URLをコピーしました')}catch(e){const area=document.createElement('textarea');area.value=url;document.body.append(area);area.select();document.execCommand('copy');area.remove();toast('URLをコピーしました')}});
refresh();setInterval(refresh,1000);

