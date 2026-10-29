// Optional live client regression test; npm install mineflayer outside the app first.
const assert=require('assert'),path=require('path'),{execFileSync}=require('child_process');
const modules=process.env.LMS_TEST_NODE_MODULES;
const mineflayer=require(path.join(modules,'mineflayer'));
const {Vec3}=require(path.join(modules,'vec3'));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const cmd=s=>execFileSync(process.env.LMS_TEST_PYTHON||'python',[path.join(__dirname,'rcon_command.py'),s],{encoding:'utf8'}).trim();
const state=()=>JSON.parse(cmd('lmsarena status'));
async function run(){
  assert(JSON.parse(cmd('lmsarena generate world 0 80 0 9 9 3 minecraft:glass minecraft:diamond_block 10 1 true false 100 10 1')).ok);
  await delay(300);
  const bot=mineflayer.createBot({host:'127.0.0.1',port:25585,username:'LMS_Test',auth:'offline',version:'1.21.1'});
  const failed=new Promise((_,reject)=>{bot.once('error',reject);bot.once('kicked',r=>reject(Error(JSON.stringify(r))));});
  await Promise.race([new Promise(r=>bot.once('spawn',r)),failed]);
  try{
    cmd('tp LMS_Test 4.5 110 4.5');
    bot.creative.startFlying();
    await delay(700);
    const Item=require(path.join(modules,'prismarine-item'))(bot.registry);
    await bot.creative.setInventorySlot(36,new Item(bot.registry.itemsByName.diamond_block.id,64));
    bot.setQuickBarSlot(0);
    await bot.lookAt(new Vec3(4.5,79,4.5),true);
    await delay(200);
    for(let i=0;i<3;i++){bot.activateItem();await delay(220);}
    assert.equal(state().filled,3,'right click from 30 blocks overhead should fill a column');
    bot.activateItem();await delay(200);
    assert.equal(state().filled,3,'no extra block above full column');
    assert(cmd('execute if block 4 83 4 air').includes('Test passed'));
    console.log('PASS client right-click at distance: manual remote fill and height cap');

    // Vanilla placement with another block type is also capped at the rim.
    cmd('tp LMS_Test 4.5 84 4.5');await delay(400);
    await bot.creative.setInventorySlot(36,new Item(bot.registry.itemsByName.stone.id,64));
    bot._client.write('block_place',{location:new Vec3(4,82,4),direction:1,hand:0,cursorX:.5,cursorY:1,cursorZ:.5,insideBlock:false,sequence:1});
    await delay(250);
    assert(cmd('execute if block 4 83 4 air').includes('Test passed'));

    // Creative instant-break must be rejected for glass frame blocks.
    cmd('tp LMS_Test 1.5 81 4.5');await delay(400);
    bot._client.write('block_dig',{status:0,location:new Vec3(-1,81,4),face:5,sequence:2});
    await delay(250);
    assert(cmd('execute if block -1 81 4 glass').includes('Test passed'));
    console.log('PASS native placement height cap and creative glass-frame break protection');
  }finally{bot.quit();}
}
const timeout=setTimeout(()=>{console.error('Client integration timed out');process.exit(1)},25000);
run().then(()=>clearTimeout(timeout)).catch(e=>{clearTimeout(timeout);console.error(e);process.exit(1)});
