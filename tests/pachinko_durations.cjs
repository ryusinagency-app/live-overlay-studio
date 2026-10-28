const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=fs.existsSync(path.join(__dirname,'overlay_pachinko.html'))?__dirname:path.dirname(__dirname);
const source=fs.readFileSync(path.join(root,'overlay_pachinko.html'),'utf8').split('<script>')[1].split('</script>')[0];
let now=0,serial=0;const timers=new Map(),audios=[];
function timeout(fn,ms){const id=++serial;timers.set(id,{fn,at:now+ms});return id}
async function advance(ms){const target=now+ms;for(;;){const due=[...timers].filter(([,t])=>t.at<=target).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();await Promise.resolve();await Promise.resolve()}now=target;await Promise.resolve();await Promise.resolve()}
class Node{
 constructor(){this.children=[];this.dataset={};this.style={setProperty(){},removeProperty(){}};this.classList={add(){},remove(){},toggle(){}};this.paused=true;this.ended=false;this.currentTime=0;this.listeners={};this.textContent=''}
 append(x){this.children.push(x)}replaceChildren(...x){this.children=x}get firstElementChild(){return this.children[0]}
 pause(){this.paused=true}play(){this.paused=false;this.ended=false;return Promise.resolve()}
 addEventListener(k,f){this.listeners[k]=f}removeEventListener(k){delete this.listeners[k]}
}
class Audio extends Node{constructor(src){super();this.src=src;audios.push(this)}}
const nodes=new Map(),ctx=vm.createContext({console,Audio,Map,Set,Promise,URLSearchParams,AbortController,Date:{now:()=>now},setTimeout:timeout,clearTimeout:id=>timers.delete(id),setInterval(){},location:{search:'?preview=1',origin:'http://localhost'},window:{addEventListener(){}},document:{getElementById(id){if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)},createElement(){return new Node()},documentElement:new Node()},getComputedStyle(){return{color:'#fff',fontSize:'30px'}}});
vm.runInContext(source,ctx);const run=code=>vm.runInContext(code,ctx);run('applyPachinkoTextRoles=()=>{}');
(async()=>{
 // Exercise every media stage and both visual formats with a deterministic clock.
 for(const key of run('pachinkoMediaStages'))for(const video of [false,true]){
  ctx.key=key;ctx.p={[key+'AnimationUrl']:'/asset.'+(video?'mp4':'png'),[key+'AudioUrl']:'/sound.mp3',[key+'ImageSeconds']:1,[key+'VideoSeconds']:3,[key+'AudioSeconds']:2,[key+'AudioLoop']:true};
  run('startStageMedia(p,key)');const visual=nodes.get('media').firstElementChild,audio=run('currentAudio');
  await advance(1000);assert.equal(visual.style.visibility==='hidden',!video,key+' independent image time');assert.equal(audio.paused,false);
  await advance(1000);assert.equal(audio.paused,true,key+' audio time');if(video)assert.equal(visual.paused,false);
  await advance(1000);assert.equal(visual.style.visibility,'hidden');if(video)assert.equal(visual.paused,true);
  run('stopMedia()');assert.equal(timers.size,0);
 }
 // A 5s image and 2s audio extend a 1s stage to exactly 5s.
 ctx.p={hitSeconds:1,hitAnimationUrl:'/five.png',hitImageSeconds:5,hitAudioUrl:'/two.mp3',hitAudioSeconds:2};
 let done=false;const stage=run("playStage(p,'hit','大当たり')").then(()=>{done=true});await advance(2000);assert(run('currentAudio.paused'));assert(!done);await advance(2999);assert(!done);await advance(1);await stage;assert(done);run('stopMedia()');
 // New scene cancels deadlines belonging to the previous scene, even with reused sound URLs.
 ctx.p={hitAnimationUrl:'/old.png',hitImageSeconds:1,hitAudioUrl:'/same.mp3',hitAudioSeconds:1,atAnimationUrl:'/new.mp4',atVideoSeconds:4,atAudioUrl:'/same.mp3',atAudioSeconds:4};
 run("startStageMedia(p,'hit')");await advance(500);run("startStageMedia(p,'at')");const current=nodes.get('media').firstElementChild;await advance(500);assert(!run('currentAudio.paused'));assert(!current.style.visibility);run('stopMedia()');await advance(4000);assert.equal(timers.size,0);
 // Legacy fallback inherits media limits; dedicated limits can override them.
 ctx.p={hitAudioUrl:'/legacy.mp3',hitAudioSeconds:4,atAnimationUrl:'/base.png',atImageSeconds:5,atHitImageSeconds:2};
 run("startPachinkoResult(p,'atHit',true,'at')");assert.equal(run('pachinkoStageWaitMs(1)'),4000);await advance(2000);assert.equal(nodes.get('media').firstElementChild.style.visibility,'hidden');assert(!run('currentAudio.paused'));await advance(2000);assert(run('currentAudio.paused'));run('stopMedia()');
 // Pre-alert visual and audio stop independently; no sleep speed scaling is introduced.
 ctx.p={preAlerts:[{textSeconds:.2,mediaSeconds:0,audioSeconds:0}],preAlert1AnimationUrl:'/alert.mp4',preAlert1VideoSeconds:1,preAlert1AudioUrl:'/alert.mp3',preAlert1AudioSeconds:3,preAlert1AudioLoop:true};
 done=false;const alert=run('playPachinkoPreAlert(p,0)').then(()=>{done=true});const video=run('alertVideo'),audio=run('alertAudio');await advance(1000);assert(video.paused);assert(!audio.paused);assert(!done);await advance(2000);await alert;assert(done&&audio.paused);assert.equal(timers.size,0);
 // Cancelling a long stage clears all asset and wait timers.
 const cancelled=run("playStage({hitSeconds:1,hitAnimationUrl:'/long.png',hitImageSeconds:600,hitAudioUrl:'/long.mp3',hitAudioSeconds:600},'hit','test')").catch(e=>e.name);run('cancelPachinkoPlayback()');assert.equal(await cancelled,'AbortError');assert.equal(timers.size,0);
 // 0 durations add no extra wait and preserve default stage timing.
 run("startStageMedia({spinAnimationUrl:'/legacy.png',spinAudioUrl:'/legacy.mp3'},'spin')");assert.equal(run('pachinkoStageWaitMs(.8)'),800);assert.equal(timers.size,0);run('stopMedia()');
 // Every stage editor exposes all three values and collects them by stage/kind.
 const editor=fs.readFileSync(path.join(root,'v6608.js'),'utf8'),i=editor.indexOf('function stageEditor(');run(editor.slice(i,editor.indexOf('\n',i)));
 for(const key of run('pachinkoMediaStages')){ctx.key=key;const html=run("stageEditor({},key,'test')");for(const kind of ['Image','Video','Audio'])assert(html.includes(`data-kind="${kind}"`),key+' '+kind)}
 console.log('PASS: all stage image/video/audio deadlines, scene extension, stale timer cancellation, same URL reuse, fallback/override, pre-alerts, legacy timing, editor fields');
})().catch(e=>{console.error(e);process.exitCode=1});
