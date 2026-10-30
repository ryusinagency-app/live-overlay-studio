const $=id=>document.getElementById(id);let current,workingEffects,giftCatalog=[];
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(j.message||'通信エラー');return j}
function toast(message,error=false){const el=$('toast');el.textContent=message;el.className=error?'show error':'show';setTimeout(()=>el.className='',2600)}
function value(id){const el=$(id);return el.type==='number'?Number(el.value):el.type==='checkbox'?el.checked:el.value}
function set(id,v){const el=$(id);if(!el||el.dataset.dirty==='1')return;if(el.type==='checkbox')el.checked=!!v;else el.value=v??''}
function render(s){current=s;const c=s.config,a=s.game.arena,m=s.game.multiplier;
 $('connection').textContent=s.status.rcon;$('connection').className='badge '+(s.status.rcon==='接続中'?'ok':'');
 $('floorHealthCard').hidden=!a.floorEnabled;$('countdownState').textContent=a.defending?`残り ${a.holdRemainingSeconds}秒`:'埋め立て中';$('worldBridgeState').textContent=s.status.lastError||s.status.worldBridge||'';
 $('health').textContent=`${a.health} / ${a.maxHealth}`;$('healthBar').style.width=`${a.maxHealth?a.health/a.maxHealth*100:0}%`;
 $('filled').textContent=`${a.filled} / ${a.capacity}`;$('fillBar').style.width=`${a.capacity?a.filled/a.capacity*100:0}%`;
 $('feverState').textContent=m.active?`${m.multiplier}倍タイム`:'通常';$('feverRemaining').textContent=m.active?`残り ${m.remainingSeconds}秒`:`次まで ${m.progress} / ${m.threshold}`;$('queued').textContent=s.status.queuedCommands;
 Object.entries(c.arena).forEach(([k,v])=>set(k,v));set('commandDelayMs',c.commandDelayMs);
 set('threshold',c.multiplier.threshold);set('durationSeconds',c.multiplier.durationSeconds);set('multiplier',c.multiplier.multiplier);set('applyFill',c.multiplier.applyFill);set('applyTnt',c.multiplier.applyTnt);set('applyWin',c.multiplier.applyWin);['Repair','Items','Resize','Countdown','Player'].forEach(k=>set('apply'+k,c.multiplier['apply'+k]));set('stackingMode',c.multiplier.stackingMode);
 set('successText',c.overlay?.successText||'WIN！');set('rconHost',c.rcon.host);set('rconPort',c.rcon.port);if($('rconPassword').value==='')set('rconPassword',c.rcon.password);set('serverSoftware',c.rcon.serverSoftware||'未判定');$('serverVersionText').textContent=c.rcon.serverVersionText||'';set('winEnabled',c.winBridge.enabled);set('winUrl',c.winBridge.url);if($('winToken').value==='')set('winToken',c.winBridge.token);
 const es=c.overlay?.effectListStyle||{};set('effectColumns',es.columns??5);set('effectCardWidth',es.cardWidth??180);set('effectCardHeight',es.cardHeight??180);set('effectGap',es.gap??8);set('effectRadius',es.borderRadius??14);set('effectBackgroundColor',es.backgroundColor||'#61294f');set('effectBorderColor',es.borderColor||'#ef334e');set('effectTextColor',es.textColor||'#ffffff');set('effectAccentColor',es.accentColor||'#a4f4bf');set('effectGlowColor',es.feverGlowColor||'#ffd34e');set('effectNameFontSize',es.nameFontSize??18);set('effectAmountFontSize',es.effectFontSize??20);set('effectDescriptionFontSize',es.descriptionFontSize??13);set('effectImageSize',es.imageSize??74);
 const local=s.localServer||{},running=local.running===true,prepared=local.prepared===true;
 $('localServerState').textContent=running?'起動中':prepared?'準備済み・停止中':'初回準備が必要';
 $('localServerMessage').textContent=local.message||'';
 $('localServerLamp').className=running?'running':prepared?'prepared':'';
 $('javaStatus').textContent=local.java?.available?(local.java.version||'Java確認済み'):'Java 21は「サーバーを準備」で自動設定されます';
 $('prepareLocalServer').disabled=running;$('startLocalServer').disabled=!prepared||running;$('stopLocalServer').disabled=!running;
 $('specialStock').textContent=`全埋めボム ${a.bombCharges||0}回 ／ 連鎖ブロック ${a.chainCharges||0}回 ／ 現在の枠 ${a.actualWidth||a.width}×${a.actualDepth||a.depth}×${a.actualHeight||a.height} ／ 規定 ${a.holdSeconds}秒`;
 if(!workingEffects){workingEffects=structuredClone(c.effects);renderEffectCards()}
 document.querySelectorAll('.effectCard').forEach(card=>{const p=s.effectPreviews?.[card.dataset.id];if(p){card.classList.toggle('fever',p.feverApplied);card.querySelector('.effectiveAmount').textContent=p.effectiveLabel}});
}
const kindOptions=[['fill','指定個数を埋める'],['fill_layers','空きのある下段から指定段数を埋める'],['fill_percent','枠全体の指定割合分を追加で埋める'],['fill_all','全埋め'],['clear_all','全消し'],['tnt','TNT'],['repair','底の耐久回復'],['shield','シールド'],['bomb','全埋めボム補充'],['chain','連鎖ブロック補充'],['resize','枠サイズ変更'],['freeze','移動停止'],['launch','上へ吹き飛ばす'],['countdown','規定カウント変更'],['clear','指定個数を消去']];
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
function playEffectSound(effect){
 if(!effect?.soundEnabled||!effect.soundUrl)return;
 const audio=new Audio(effect.soundUrl);audio.volume=Math.max(0,Math.min(1,Number(effect.soundVolume??100)/100));audio.play().catch(()=>toast('音声を再生できませんでした',true));
 const seconds=Number(effect.soundSeconds||0);if(seconds>0)setTimeout(()=>{audio.pause();audio.currentTime=0},seconds*1000);
}
function collectEffectCards(){
 const result={};
 document.querySelectorAll('.effectCard').forEach(card=>{const e={...(workingEffects[card.dataset.id]||{})};
 card.querySelectorAll('[data-effect-key]').forEach(el=>e[el.dataset.effectKey]=el.type==='checkbox'?el.checked:el.type==='number'?Number(el.value):el.value);
 result[card.dataset.id]=e;});
 workingEffects=result;$('effectsJson').value=JSON.stringify(result,null,2);return result;
}
function renderEffectCards(){
 const host=$('effectCards');host.replaceChildren();
 for(const [id,e] of Object.entries(workingEffects||{})){
  const card=document.createElement('div');card.className='effectCard';card.dataset.id=id;
  card.draggable=true;
  const main=document.createElement('div');main.className='effectMain';
  const img=document.createElement('img');img.src=e.giftImageUrl||'';img.alt='';
  const del=document.createElement('button');del.className='danger';del.textContent='削除';del.onclick=()=>{collectEffectCards();delete workingEffects[id];renderEffectCards()};
  const tryButton=document.createElement('button');tryButton.className='accent effectTestButton';tryButton.textContent='この効果をテスト';tryButton.onclick=()=>testConfigured(id);
  const drag=document.createElement('button');drag.type='button';drag.className='dragHandle';drag.textContent='↕ 移動';drag.title='ドラッグして並び替え';
  drag.onpointerdown=()=>card.dataset.dragReady='1';
  const up=document.createElement('button');up.type='button';up.textContent='↑';up.title='ひとつ上へ';up.onclick=()=>moveEffectCard(card,-1);
  const down=document.createElement('button');down.type='button';down.textContent='↓';down.title='ひとつ下へ';down.onclick=()=>moveEffectCard(card,1);
  main.append(img,field('表示名','text',e.name||e.giftName||id,'name'),field('効果','select',e.kind||'fill','kind',kindOptions),drag,up,down,tryButton,del);
  const amount=document.createElement('strong');amount.className='effectiveAmount';amount.textContent='保存後に反映';
  const settings=document.createElement('div');settings.className='form effectSettings';
  function add(label,type,key,fallback,kinds,options){const l=field(label,type,e[key]??fallback,key,options);if(kinds)l.dataset.kinds=kinds.join(',');settings.append(l);}
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
  const hint=document.createElement('p');hint.className='note';hint.textContent='表示文で {amount}＝確定数量、{seconds}＝秒数、{strength}＝強さ、{name}＝ギフター名、{gift}＝ギフト名を使用できます。例：TNT{amount}個 ／ TNTやめろ！';
  const kind=main.querySelector('select');const visibility=()=>settings.querySelectorAll('[data-kinds]').forEach(l=>l.hidden=!l.dataset.kinds.split(',').includes(kind.value));kind.onchange=visibility;visibility();
  card.append(main,amount,settings,design,hint);host.append(card);
 }
 enableEffectDrag();
 $('effectsJson').value=JSON.stringify(workingEffects,null,2);
}
function moveEffectCard(card,direction){const sibling=direction<0?card.previousElementSibling:card.nextElementSibling;if(!sibling)return;if(direction<0)card.parentElement.insertBefore(card,sibling);else card.parentElement.insertBefore(sibling,card);collectEffectCards()}
function enableEffectDrag(){let dragging=null;document.querySelectorAll('.effectCard').forEach(card=>{card.ondragstart=e=>{if(card.dataset.dragReady!=='1'){e.preventDefault();return}dragging=card;card.classList.add('dragging');e.dataTransfer.effectAllowed='move'};card.ondragend=()=>{delete card.dataset.dragReady;card.classList.remove('dragging');dragging=null;collectEffectCards()};card.ondragover=e=>{if(!dragging||dragging===card)return;e.preventDefault();const box=card.getBoundingClientRect();card.parentElement.insertBefore(dragging,e.clientY<box.top+box.height/2?card:card.nextElementSibling)}})}
function effectListStyle(){return {columns:value('effectColumns'),cardWidth:value('effectCardWidth'),cardHeight:value('effectCardHeight'),gap:value('effectGap'),borderRadius:value('effectRadius'),backgroundColor:value('effectBackgroundColor'),borderColor:value('effectBorderColor'),textColor:value('effectTextColor'),accentColor:value('effectAccentColor'),feverGlowColor:value('effectGlowColor'),nameFontSize:value('effectNameFontSize'),effectFontSize:value('effectAmountFontSize'),descriptionFontSize:value('effectDescriptionFontSize'),imageSize:value('effectImageSize')}}
function addGift(gift){collectEffectCards();const id=String(gift.id||gift.name);if(!id)return;workingEffects[id]={...(workingEffects[id]||{}),giftId:String(gift.id||''),giftName:String(gift.name||''),giftImageUrl:String(gift.imageUrl||''),name:String(gift.name||'ギフト効果'),kind:'fill',amount:1,win:0,description:'1ブロック埋めます'};$('giftDialog').close();renderEffectCards()}
function renderGiftCatalog(){const q=$('giftSearch').value.trim().toLowerCase();$('giftCatalog').replaceChildren(...giftCatalog.filter(g=>!q||String(g.name).toLowerCase().includes(q)||String(g.price).includes(q)).map(g=>{const b=document.createElement('button');b.className='giftChoice';const img=document.createElement('img');img.src=g.imageUrl||'';const n=document.createElement('b');n.textContent=g.name||'ギフト';const p=document.createElement('small');p.textContent=`${g.price||0}コイン`;b.append(img,n,p);b.onclick=()=>addGift(g);return b}))}
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
$('resetCardStyles').onclick=async()=>{collectEffectCards();Object.values(workingEffects).forEach(e=>e.useCustomStyle=false);renderEffectCards();await save({effects:workingEffects,overlay:{effectListStyle:effectListStyle()}},'全カードを一括デザインへ揃えました');workingEffects=undefined};
$('applyEffectsJson').onclick=()=>{try{workingEffects=JSON.parse($('effectsJson').value);renderEffectCards();toast('JSONを画面へ反映しました')}catch(e){toast('JSONの形式を確認してください',true)}};
$('addGiftEffect').onclick=async()=>{try{const r=await api('/api/gift-catalog');giftCatalog=r.gifts||[];renderGiftCatalog();$('giftDialog').showModal()}catch(e){toast(e.message,true)}};
$('closeGiftDialog').onclick=()=>$('giftDialog').close();$('giftSearch').oninput=renderGiftCatalog;
$('saveFever').onclick=()=>save({multiplier:{threshold:value('threshold'),durationSeconds:value('durationSeconds'),multiplier:value('multiplier'),applyFill:value('applyFill'),applyTnt:value('applyTnt'),applyWin:value('applyWin'),applyRepair:value('applyRepair'),applyItems:value('applyItems'),applyResize:value('applyResize'),applyCountdown:value('applyCountdown'),applyPlayer:value('applyPlayer'),stackingMode:value('stackingMode')}});
async function localServerAction(path,body,message){const buttons=['prepareLocalServer','startLocalServer','stopLocalServer'].map($);buttons.forEach(b=>b.disabled=true);toast(message);try{const r=await api(path,body||{});render(r.state);toast(r.message||'完了しました')}catch(e){toast(e.message,true)}finally{setTimeout(refresh,400)}}
$('prepareLocalServer').onclick=()=>localServerAction('/api/local-server/prepare',{eulaAccepted:value('eulaAccepted')},'サーバーを準備しています');
$('startLocalServer').onclick=()=>localServerAction('/api/local-server/start',{},'Minecraftサーバーを起動しています');
$('stopLocalServer').onclick=()=>localServerAction('/api/local-server/stop',{},'ワールドを保存して停止しています');
$('saveConnection').onclick=()=>save({rcon:{host:value('rconHost'),port:value('rconPort'),password:value('rconPassword')}});
$('testConnection').onclick=async()=>{try{const r=await api('/api/rcon/test',{});toast(r.message||'接続できました');refresh()}catch(e){toast(e.message,true)}};
$('detectServer').onclick=async()=>{try{await save({rcon:{host:value('rconHost'),port:value('rconPort'),password:value('rconPassword')}},'接続設定を保存しました');const r=await api('/api/rcon/detect',{});set('serverSoftware',r.software);$('serverVersionText').textContent=r.detail||'';toast(`${r.software} と判定しました`)}catch(e){toast(e.message,true)}};
$('saveWin').onclick=()=>save({winBridge:{enabled:value('winEnabled'),url:value('winUrl'),token:value('winToken')}});
refresh();setInterval(refresh,1000);

