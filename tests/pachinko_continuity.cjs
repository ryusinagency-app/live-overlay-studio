const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=fs.existsSync(path.join(__dirname,'overlay_pachinko.html'))?__dirname:path.dirname(__dirname);
const script=fs.readFileSync(path.join(root,'overlay_pachinko.html'),'utf8').split('<script>')[1].split('</script>')[0];
function fixture(){
 const audios=[],nodes=new Map(),frames=[],phases=[];
 class Node{
  constructor(){this.children=[];this.style={setProperty(){},removeProperty(){}};this.classList={add(){},remove(){},toggle(){}};this.dataset={};this.textContent='';this.paused=true;this.ended=false;this.currentTime=0;this.listeners={}}
  append(x){this.children.push(x)}replaceChildren(...x){this.children=x}get firstElementChild(){return this.children[0]}
  pause(){this.paused=true}play(){this.paused=false;return Promise.resolve()}addEventListener(k,f){this.listeners[k]=f}removeEventListener(k){delete this.listeners[k]}
 }
 class Audio extends Node{constructor(src){super();this.src=src;audios.push(this)}}
 const ctx=vm.createContext({console,frames,phases,Audio,Map,Set,Promise,URLSearchParams,setTimeout,clearTimeout,setInterval(){},location:{search:'?preview=1',origin:'http://localhost'},window:{addEventListener(){}},document:{getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)},createElement(){return new Node()},documentElement:new Node()},getComputedStyle(){return{color:'#fff',fontSize:'30px'}}});
 vm.runInContext(script,ctx);const run=s=>vm.runInContext(s,ctx);
 run(`applyPachinkoTextRoles=()=>{};sleep=async ms=>{if(currentAudio&&!currentAudio.paused)currentAudio.currentTime+=ms/1000};
  let roundUnderTest=-1;const actualPhaseSpins=animatePhaseSpins;animatePhaseSpins=async(...args)=>{roundUnderTest++;phases.push(args[1]);await actualPhaseSpins(...args)};
  const actualShowText=showText;showText=function(...args){frames.push({round:roundUnderTest,status:args[0]||'',number:args[1]||'',detail:args[2]||'',total:args[3]||'',audio:currentAudio?.src,time:currentAudio?.currentTime});return actualShowText(...args)};`);
 return{ctx,run,frames,audios};
}
function round(phase,kind,continued=true,total=100){return{phase,mode:'continue',resultKind:kind,continued,win:kind==='win'?10:0,hitSpin:kind==='win'?1:0,spins:1,total}}
(async()=>{
 for(const phase of ['at','upper','lt'])for(const enabled of [false,true]){
  const f=fixture();f.ctx.p={id:'p',name:'test',reachEnabled:false,spinSeconds:.05,spinDisplaySeconds:.2,[phase+'EnterEnabled']:enabled,[phase+'EnterAudioUrl']:'/entry.mp3',[phase+'AudioUrl']:'/bg.mp3',[phase+'SpinAudioUrl']:'/bg.mp3',stopAudioUrl:'/stop.mp3',hitAudioUrl:'/win.mp3'};
  f.ctx.event={id:1,patternId:'p',preview:true,hitSpin:1,spins:1,route:'at',initialWin:10,total:110,rounds:[round(phase,'continue-miss'),round(phase,'continue-miss'),round(phase,'win')]};
  await f.run('playEvent({pachinkoGacha:{patterns:[p]}},event)');
  const label={at:'ST突入',upper:'上位ST突入',lt:'ラッキートリガー突入'}[phase];
  assert.equal(f.frames.filter(x=>x.status===label).length,enabled?1:0,phase+' entry toggle is authoritative');
  assert.equal(f.audios.filter(a=>a.src==='/entry.mp3').length,enabled?1:0);
  for(const index of [0,1])for(const frame of f.frames.filter(x=>x.round===index)){
   assert.equal(frame.total,'',phase+' continuing miss must not display aggregate WIN');
   assert(!frame.number.includes('WIN'));assert(!frame.detail.includes('合計'));
  }
  const spins=f.frames.filter(x=>x.audio==='/bg.mp3'&&x.status.includes('抽選中'));
  assert(spins.length>=3);for(let i=1;i<spins.length;i++)assert(spins[i].time>=spins[i-1].time,'background must resume rather than restart after a stop sound');
  assert(f.frames.some(x=>x.round===2&&x.number.includes('WIN')),'real WIN still shows its result');
  assert.equal(f.frames.filter(x=>x.status==='終了').length,1,'final result is shown once at end');
 }
 // A dedicated continuing-miss effect is still supported, without aggregate WIN.
 const f=fixture();f.ctx.p={id:'p',reachEnabled:false,upperAudioUrl:'/bg.mp3',upperContinueMissAnimationUrl:'/miss.png',upperContinueMissAudioUrl:'/miss.mp3'};
 f.ctx.event={id:2,patternId:'p',preview:true,hitSpin:1,spins:1,route:'at',total:100,rounds:[round('upper','continue-miss'),round('upper','end-miss',false)]};
 await f.run('playEvent({pachinkoGacha:{patterns:[p]}},event)');
 const miss=f.frames.find(x=>x.status==='はずれ・継続！');assert(miss&&miss.audio==='/miss.mp3');assert.equal(miss.total,'');
 // Same music/video across normal stage names preserves the actual player and position.
 const g=fixture();g.ctx.p={upperAnimationUrl:'/bg.mp4',upperAudioUrl:'/bg.mp3',upperSpinAnimationUrl:'/bg.mp4',upperSpinAudioUrl:'/bg.mp3'};
 g.run("startStageMedia(p,'upper');currentAudio.currentTime=12;currentVideo.currentTime=9");const audio=g.run('currentAudio'),video=g.run('currentVideo');g.run("startStageMedia(p,'upperSpin')");assert.strictEqual(g.run('currentAudio'),audio);assert.equal(audio.currentTime,12);assert.strictEqual(g.run('currentVideo'),video);assert.equal(video.currentTime,9);g.run('stopMedia()');
 console.log('PASS: all ST entry toggles, no forced entry, continuing misses omit aggregate results, optional miss media retained, BGM/video continuity, real WIN and final end preserved');
})().catch(e=>{console.error(e);process.exitCode=1});
