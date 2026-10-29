const $=id=>document.getElementById(id);let current,workingEffects,giftCatalog=[];
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const j=await r.json();if(!r.ok)throw new Error(j.message||'通信エラー');return j}
function toast(message,error=false){const el=$('toast');el.textContent=message;el.className=error?'show error':'show';setTimeout(()=>el.className='',2600)}
function value(id){const el=$(id);return el.type==='number'?Number(el.value):el.type==='checkbox'?el.checked:el.value}
function set(id,v){const el=$(id);if(!el)return;if(el.type==='checkbox')el.checked=!!v;else el.value=v??''}
function render(s){current=s;const c=s.config,a=s.game.arena,m=s.game.multiplier;
 $('connection').textContent=s.status.rcon;$('connection').className='badge '+(s.status.rcon==='接続中'?'ok':'');
 $('health').textContent=`${a.health} / ${a.maxHealth}`;$('healthBar').style.width=`${a.maxHealth?a.health/a.maxHealth*100:0}%`;
 $('filled').textContent=`${a.filled} / ${a.capacity}`;$('fillBar').style.width=`${a.capacity?a.filled/a.capacity*100:0}%`;
 $('feverState').textContent=m.active?`${m.multiplier}倍タイム`:'通常';$('feverRemaining').textContent=m.active?`残り ${m.remainingSeconds}秒`:`次まで ${m.progress} / ${m.threshold}`;$('queued').textContent=s.status.queuedCommands;
 Object.entries(c.arena).forEach(([k,v])=>set(k,v));set('commandDelayMs',c.commandDelayMs);
 set('threshold',c.multiplier.threshold);set('durationSeconds',c.multiplier.durationSeconds);set('multiplier',c.multiplier.multiplier);set('applyFill',c.multiplier.applyFill);set('applyTnt',c.multiplier.applyTnt);set('applyWin',c.multiplier.applyWin);
 set('rconHost',c.rcon.host);set('rconPort',c.rcon.port);if($('rconPassword').value==='')set('rconPassword',c.rcon.password);set('serverSoftware',c.rcon.serverSoftware||'未判定');$('serverVersionText').textContent=c.rcon.serverVersionText||'';set('winEnabled',c.winBridge.enabled);set('winUrl',c.winBridge.url);if($('winToken').value==='')set('winToken',c.winBridge.token);
 const local=s.localServer||{},running=local.running===true,prepared=local.prepared===true;
 $('localServerState').textContent=running?'起動中':prepared?'準備済み・停止中':'初回準備が必要';
 $('localServerMessage').textContent=local.message||'';
 $('localServerLamp').className=running?'running':prepared?'prepared':'';
 $('javaStatus').textContent=local.java?.available?(local.java.version||'Java確認済み'):'Java 21は「サーバーを準備」で自動設定されます';
 $('prepareLocalServer').disabled=running;$('startLocalServer').disabled=!prepared||running;$('stopLocalServer').disabled=!running;
 if(!workingEffects){workingEffects=structuredClone(c.effects);renderEffectCards()}
 $('testButtons').replaceChildren(...Object.entries(c.effects).map(([id,e])=>{const b=document.createElement('button');b.textContent=e.name||id;b.onclick=()=>test(id);return b}));
}
const kindOptions=[['fill','埋め立て'],['fill_all','全埋め'],['tnt','TNT'],['repair','耐久回復'],['shield','シールド'],['countdown','カウント変更'],['clear','ブロック消去']];
function field(label,type,value,cls){const l=document.createElement('label');l.textContent=label;const el=document.createElement(type==='select'?'select':'input');el.className=cls;if(type!=='select')el.type=type;el.value=value??'';l.append(el);return l}
function collectEffectCards(){const result={};document.querySelectorAll('.effectCard').forEach(card=>{const id=card.dataset.id;const old=workingEffects[id]||{};result[id]={...old,name:card.querySelector('.effectName').value,kind:card.querySelector('.effectKind').value,amount:Number(card.querySelector('.effectAmount').value||0),win:Number(card.querySelector('.effectWin').value||0),description:card.querySelector('.effectDescription').value}});workingEffects=result;$('effectsJson').value=JSON.stringify(result,null,2);return result}
function renderEffectCards(){const host=$('effectCards');host.replaceChildren();for(const [id,e] of Object.entries(workingEffects||{})){const card=document.createElement('div');card.className='effectCard';card.dataset.id=id;const img=document.createElement('img');img.src=e.giftImageUrl||'';img.alt='';const name=field('表示名','text',e.name||e.giftName||id,'effectName');const kind=field('効果','select','','effectKind');kind.querySelector('select').replaceChildren(...kindOptions.map(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;o.selected=e.kind===v;return o}));const amount=field('数量','number',e.amount??1,'effectAmount');const win=field('WIN','number',e.win??0,'effectWin');const del=document.createElement('button');del.className='danger';del.textContent='削除';del.onclick=()=>{delete workingEffects[id];renderEffectCards()};const desc=field('視聴者向け説明','text',e.description||'','effectDescription');desc.classList.add('description');card.append(img,name,kind,amount,win,del,desc);host.append(card)}$('effectsJson').value=JSON.stringify(workingEffects,null,2)}
function addGift(gift){const id=String(gift.id||gift.name);if(!id)return;workingEffects[id]={...(workingEffects[id]||{}),giftId:String(gift.id||''),giftName:String(gift.name||''),giftImageUrl:String(gift.imageUrl||''),name:String(gift.name||'ギフト効果'),kind:'fill',amount:1,win:0,description:'1ブロック埋めます'};$('giftDialog').close();renderEffectCards()}
function renderGiftCatalog(){const q=$('giftSearch').value.trim().toLowerCase();$('giftCatalog').replaceChildren(...giftCatalog.filter(g=>!q||String(g.name).toLowerCase().includes(q)||String(g.price).includes(q)).map(g=>{const b=document.createElement('button');b.className='giftChoice';const img=document.createElement('img');img.src=g.imageUrl||'';const n=document.createElement('b');n.textContent=g.name||'ギフト';const p=document.createElement('small');p.textContent=`${g.price||0}コイン`;b.append(img,n,p);b.onclick=()=>addGift(g);return b}))}
async function refresh(){try{render(await api('/api/state'))}catch(e){$('connection').textContent='停止';}}
async function save(body,message='保存しました'){try{const r=await api('/api/config',body);render(r.state);toast(message)}catch(e){toast(e.message,true)}}
async function test(id){try{const r=await api('/api/test-effect',{giftId:id,coins:0});toast(r.message||'テストを開始しました');refresh()}catch(e){toast(e.message,true)}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('[data-page]').forEach(p=>p.hidden=p.dataset.page!==b.dataset.tab)});
$('saveArena').onclick=()=>save({arena:{x:value('x'),y:value('y'),z:value('z'),width:value('width'),depth:value('depth'),height:value('height'),frameBlock:value('frameBlock'),fillBlock:value('fillBlock'),maxHealth:value('maxHealth'),holdSeconds:value('holdSeconds'),holdWin:value('holdWin'),clearAfterSuccess:value('clearAfterSuccess')},commandDelayMs:value('commandDelayMs')});
$('buildArena').onclick=async()=>{try{const r=await api('/api/arena/build',{});toast(`${r.queued}件の枠生成処理を開始しました`)}catch(e){toast(e.message,true)}};
$('saveEffects').onclick=async()=>{collectEffectCards();await save({effects:workingEffects});workingEffects=undefined};
$('applyEffectsJson').onclick=()=>{try{workingEffects=JSON.parse($('effectsJson').value);renderEffectCards();toast('JSONを画面へ反映しました')}catch(e){toast('JSONの形式を確認してください',true)}};
$('addGiftEffect').onclick=async()=>{try{const r=await api('/api/gift-catalog');giftCatalog=r.gifts||[];renderGiftCatalog();$('giftDialog').showModal()}catch(e){toast(e.message,true)}};
$('closeGiftDialog').onclick=()=>$('giftDialog').close();$('giftSearch').oninput=renderGiftCatalog;
$('saveFever').onclick=()=>save({multiplier:{threshold:value('threshold'),durationSeconds:value('durationSeconds'),multiplier:value('multiplier'),applyFill:value('applyFill'),applyTnt:value('applyTnt'),applyWin:value('applyWin')}});
async function localServerAction(path,body,message){const buttons=['prepareLocalServer','startLocalServer','stopLocalServer'].map($);buttons.forEach(b=>b.disabled=true);toast(message);try{const r=await api(path,body||{});render(r.state);toast(r.message||'完了しました')}catch(e){toast(e.message,true)}finally{setTimeout(refresh,400)}}
$('prepareLocalServer').onclick=()=>localServerAction('/api/local-server/prepare',{eulaAccepted:value('eulaAccepted')},'サーバーを準備しています');
$('startLocalServer').onclick=()=>localServerAction('/api/local-server/start',{},'Minecraftサーバーを起動しています');
$('stopLocalServer').onclick=()=>localServerAction('/api/local-server/stop',{},'ワールドを保存して停止しています');
$('saveConnection').onclick=()=>save({rcon:{host:value('rconHost'),port:value('rconPort'),password:value('rconPassword')}});
$('testConnection').onclick=async()=>{try{const r=await api('/api/rcon/test',{});toast(r.message||'接続できました');refresh()}catch(e){toast(e.message,true)}};
$('detectServer').onclick=async()=>{try{await save({rcon:{host:value('rconHost'),port:value('rconPort'),password:value('rconPassword')}},'接続設定を保存しました');const r=await api('/api/rcon/detect',{});set('serverSoftware',r.software);$('serverVersionText').textContent=r.detail||'';toast(`${r.software} と判定しました`)}catch(e){toast(e.message,true)}};
$('saveWin').onclick=()=>save({winBridge:{enabled:value('winEnabled'),url:value('winUrl'),token:value('winToken')}});
refresh();setInterval(refresh,1000);

