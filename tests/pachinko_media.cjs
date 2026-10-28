const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=fs.existsSync(path.join(__dirname,'overlay_pachinko.html'))?__dirname:path.dirname(__dirname);
const source=fs.readFileSync(path.join(root,'overlay_pachinko.html'),'utf8').split('<script>')[1].split('</script>')[0];
const audios=[];
class Node{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.style={setProperty(){},removeProperty(){}};this.classList={add(){},remove(){},toggle(){}};this.paused=true;this.ended=false;this.currentTime=0;this.listeners={};this.textContent='';}
 append(x){this.children.push(x)} replaceChildren(...x){this.children=x} get firstElementChild(){return this.children[0]}
 pause(){this.paused=true} play(){this.paused=false;this.ended=false;this.plays=(this.plays||0)+1;return Promise.resolve()}
 addEventListener(key,fn){this.listeners[key]=fn} removeEventListener(key){delete this.listeners[key]}
}
class Audio extends Node{constructor(url){super('audio');this.src=url;audios.push(this)}}
const nodes=new Map(),ctx=vm.createContext({console,Audio,Map,Set,Promise,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval(){},location:{search:'?preview=1',origin:'http://localhost'},window:{addEventListener(){}},document:{getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)},createElement(tag){return new Node(tag)},documentElement:new Node()},getComputedStyle(){return {color:'#fff',fontSize:'30px'}}});
vm.runInContext(source,ctx);
const run=code=>vm.runInContext(code,ctx);
run(`sleep=async()=>{};applyPachinkoTextRoles=()=>{};`);
(async()=>{
 for(const phase of ['at','upper','lt']){
  ctx.p={id:'p',reachEnabled:false,stopAudioUrl:'/stop.mp3',stopAudioLoop:true,[phase+'AudioUrl']:'/background.mp3',[phase+'HitAudioUrl']:'/'+phase+'-win.mp3',[phase+'HitAnimationUrl']:'/'+phase+'-win.png',[phase+'HitAudioLoop']:false};
  await run(`animatePachinkoTurn(p,{hit:true,seconds:.05,label:'ST',progress:'',mediaKey:'${phase}',displaySeconds:.2})`);
  assert(audios.filter(a=>a.src==='/stop.mp3').every(a=>a.paused),'stop sound ends with settled-digit display');
  run(`startPachinkoResult(p,'${phase}Hit',true,'${phase}')`);
  assert.equal(run('currentAudio.src'),'/'+phase+'-win.mp3');assert.equal(run('currentAudio.loop'),false);
  assert.equal(nodes.get('media').firstElementChild.src,'/'+phase+'-win.png');
  for(const kind of ['Miss','ContinueMiss','EndMiss']){
   ctx.p[phase+kind+'AudioUrl']='/'+phase+kind+'.mp3';ctx.p[phase+kind+'AnimationUrl']='/'+phase+kind+'.mp4';ctx.p[phase+kind+'VideoLoop']=false;
   run(`startPachinkoResult(p,'${phase+kind}',false,'${phase}')`);
   assert.equal(run('currentAudio.src'),'/'+phase+kind+'.mp3');assert.equal(run('currentVideo.loop'),false);
  }
  run('stopMedia()');
 }
 ctx.p={id:'p',hitAudioUrl:'/legacy-hit.mp3',hitAudioVolume:42,hitAudioLoop:false,atAnimationUrl:'/legacy-bg.png',stopAudioUrl:'/stop.mp3'};
 run(`startPachinkoResult(p,'atHit',true,'at')`);
 assert.equal(run('currentAudio.src'),'/legacy-hit.mp3');assert.equal(run('currentAudio.volume'),.42);assert.equal(run('currentAudio.loop'),false);
 assert.equal(nodes.get('media').firstElementChild.src,'/legacy-bg.png');
 run(`activePattern=p;applyPachinkoLiveVolumes({...p,hitAudioVolume:23})`);assert.equal(run('currentAudio.volume'),.23);
 run('stopMedia()');
 ctx.p={spinAudioUrl:'/once.mp3',spinAudioLoop:false,stopAudioUrl:'/once.mp3',stopAudioLoop:false};
 run(`startStageMedia(p,'spin');currentAudio.ended=true;currentAudio.paused=true;`);const once=run('currentAudio');const plays=once.plays;
 run(`startStageMedia(p,'spin')`);assert.equal(once.plays,plays,'one-shot is not silently restarted on repeated polls/turn calls');
 run(`startStageMedia(p,'stop')`);assert(once.plays>plays,'same URL restarts at a different logical stage');run('stopMedia()');
 // Complete actual multi-phase flow. Every WIN is paired with its phase-specific audio.
 ctx.p={id:'p',name:'test',reachEnabled:false,spinSeconds:.05,spinDisplaySeconds:.2,stopAudioUrl:'/stop.mp3',stopAudioLoop:true,hitAudioUrl:'/normal-win.mp3',atHitAudioUrl:'/at-win.mp3',upperHitAudioUrl:'/upper-win.mp3',ltHitAudioUrl:'/lt-win.mp3',atResultSeconds:.2,upperResultSeconds:.2,luckyTriggerResultSeconds:.2};
 ctx.wins=[];run(`const originalShowText=showText;showText=function(...args){originalShowText(...args);if(String(args[1]).includes('WIN'))wins.push({audio:currentAudio?.src,stopPlaying:stageAudioPlayers.get('/stop.mp3')?.paused===false})};`);
 await run(`playEvent({pachinkoGacha:{patterns:[p]}},{id:1,patternId:'p',preview:true,hitSpin:1,spins:1,route:'hit',initialWin:10,rounds:['at','upper','lt'].map(phase=>({phase,spins:1,hitSpin:1,continued:true,win:5,total:15})),total:25})`);
 for(const phase of ['at','upper','lt'])assert(ctx.wins.some(w=>w.audio==='/'+phase+'-win.mp3'&&!w.stopPlaying),'correct WIN media for '+phase);
 assert(audios.every(a=>a.paused),'all tracks stop after the event');
 // Looping pre-alerts with unspecified duration finish at their display boundary.
 ctx.p={preAlerts:[{textSeconds:.2,mediaSeconds:.2,audioSeconds:0}],preAlert1AudioUrl:'/alert.mp3',preAlert1AudioLoop:true,preAlert1AnimationUrl:'/alert.mp4',preAlert1VideoLoop:false};
 await run('playPachinkoPreAlert(p,0)');assert(audios.at(-1).paused);assert.equal(audios.at(-1).loop,true);
 // Cancellation also releases a looping result track.
 run(`startPachinkoResult({atHitAudioUrl:'/loop-win.mp3',atHitAudioLoop:true},'atHit',true,'at');cancelPachinkoPlayback()`);assert(audios.at(-1).paused);
 // Editor offers both loop choices for every stage and preview entries.
 const editor=fs.readFileSync(path.join(root,'v6608.js'),'utf8');
 const start=editor.indexOf('function stageEditor('),end=editor.indexOf('\n',start);
 vm.runInContext(editor.slice(start,end),ctx);
 for(const key of [...run('pachinkoMediaStages')]){
  const html=run(`stageEditor({${JSON.stringify(key+'AudioLoop')}:false,${JSON.stringify(key+'VideoLoop')}:false},${JSON.stringify(key)},'test')`);
  assert(html.includes('pachinkoStageAudioLoop'));assert(html.includes('pachinkoStageVideoLoop'));
  assert(!new RegExp('pachinkoStageAudioLoop[^>]+checked').test(html));
 }
 console.log('PASS: stop lifecycle, ST/upper/LT result media, loop on/off, legacy fallback, one-shot completion, pre-alert loop bound, cancellation, editor controls');
})().catch(e=>{console.error(e);process.exitCode=1});
