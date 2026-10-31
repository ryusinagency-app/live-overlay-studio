package studio.liveminecraft;

import com.google.gson.Gson;
import java.util.*;
import org.bukkit.*;
import org.bukkit.attribute.Attribute;
import org.bukkit.block.Block;
import org.bukkit.command.*;
import org.bukkit.entity.*;
import org.bukkit.event.*;
import org.bukkit.event.block.*;
import org.bukkit.event.entity.*;
import org.bukkit.event.player.*;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.potion.*;
import org.bukkit.scheduler.BukkitRunnable;
import org.bukkit.util.Vector;

/** Authoritative protected mountain-climb game for Paper 1.21.1. */
public final class MountainPlugin extends JavaPlugin implements Listener, CommandExecutor {
    private final Gson json=new Gson();
    private World world;
    private Location start, goal;
    private double goalRadius=4;
    private int checkpointRise=20, win=1;
    private boolean active=false, daylight=true, clearWeather=true, checkpointsEnabled=true, deathMinusWin=false, guideEnabled=true;
    private int goalHoldSeconds=5;
    private final Map<UUID,Integer> goalHold=new HashMap<>();
    private final Map<UUID,Location> checkpoints=new HashMap<>();
    private final Map<UUID,Integer> checkpointLevels=new HashMap<>();
    private final Set<UUID> gameMobs=new HashSet<>(), vehicles=new HashSet<>();
    private final List<Map<String,Object>> wins=new ArrayList<>();
    private final Map<UUID,Long> gunCooldown=new HashMap<>(), gunReloadUntil=new HashMap<>(), invulnerableUntil=new HashMap<>();
    private final Map<UUID,Double> projectileDamage=new HashMap<>();
    private NamespacedKey gunTypeKey,gunAmmoKey,gunDamageKey,gunIntervalKey,gunMagazineKey,gunUsedKey,gunReloadKey;

    @Override public void onEnable(){
        gunTypeKey=new NamespacedKey(this,"gun_type");gunAmmoKey=new NamespacedKey(this,"gun_ammo");gunDamageKey=new NamespacedKey(this,"gun_damage");gunIntervalKey=new NamespacedKey(this,"gun_interval");gunMagazineKey=new NamespacedKey(this,"gun_magazine");gunUsedKey=new NamespacedKey(this,"gun_used");gunReloadKey=new NamespacedKey(this,"gun_reload");
        getServer().getPluginManager().registerEvents(this,this);
        Objects.requireNonNull(getCommand("lmsmountain")).setExecutor(this);
        restore();
        getServer().getScheduler().runTaskTimer(this,this::tick,1,20);
    }

    private void restore(){
        String worldName=getConfig().getString("world","");
        world=Bukkit.getWorld(worldName);
        if(world==null)return;
        start=location("start");goal=location("goal");goalRadius=getConfig().getDouble("goalRadius",4);
        checkpointRise=getConfig().getInt("checkpointRise",20);win=getConfig().getInt("win",1);goalHoldSeconds=getConfig().getInt("goalHoldSeconds",5);checkpointsEnabled=getConfig().getBoolean("checkpointsEnabled",true);deathMinusWin=getConfig().getBoolean("deathMinusWin",false);guideEnabled=getConfig().getBoolean("guideEnabled",true);
        active=start!=null&&goal!=null;
    }
    private Location location(String key){
        if(!getConfig().contains(key+".x"))return null;
        return new Location(world,getConfig().getDouble(key+".x"),getConfig().getDouble(key+".y"),getConfig().getDouble(key+".z"));
    }
    private void storeLocation(String key,Location at){
        getConfig().set(key+".x",at.getX());getConfig().set(key+".y",at.getY());getConfig().set(key+".z",at.getZ());
    }
    private Player target(String name){
        Player p=name==null?null:Bukkit.getPlayerExact(name);
        if(p==null&&world!=null&&!world.getPlayers().isEmpty())p=world.getPlayers().get(0);
        return p;
    }
    private void tick(){
        if(world==null)return;
        if(daylight)world.setTime(6000);
        if(clearWeather){world.setStorm(false);world.setThundering(false);world.setWeatherDuration(0);}
        if(!active)return;
        world.spawnParticle(Particle.HAPPY_VILLAGER,goal.clone().add(0,1,0),12,goalRadius/2,1,goalRadius/2,.02);
        for(Player p:world.getPlayers()){
            if(checkpointsEnabled){
                int level=(int)Math.floor((p.getLocation().getY()-start.getY())/Math.max(1,checkpointRise));
                if(level>checkpointLevels.getOrDefault(p.getUniqueId(),-1)){
                    checkpoints.put(p.getUniqueId(),p.getLocation());checkpointLevels.put(p.getUniqueId(),level);
                    p.sendMessage("§aチェックポイント更新：高度 "+p.getLocation().getBlockY());
                }
            }
            if(guideEnabled){
                p.setCompassTarget(goal);
                Vector toward=goal.toVector().subtract(p.getLocation().toVector()).normalize();
                for(int i=2;i<=10;i+=2)world.spawnParticle(Particle.END_ROD,p.getEyeLocation().add(toward.clone().multiply(i)),1,0,0,0,0);
            }
            if(p.getLocation().distanceSquared(goal)<=goalRadius*goalRadius){
                int held=goalHold.getOrDefault(p.getUniqueId(),0)+1;goalHold.put(p.getUniqueId(),held);
                int left=Math.max(0,goalHoldSeconds-held);
                if(left>0){p.sendTitle("§e§l"+left,"§fゴール地点に滞在",0,25,0);p.playSound(p,Sound.BLOCK_NOTE_BLOCK_HAT,.8f,1.4f);}
                else finish(p);
            }else goalHold.remove(p.getUniqueId());
        }
    }
    private void finish(Player p){
        active=false;
        wins.add(Map.of("eventId",UUID.randomUUID().toString(),"win",win,"reason","山頂ゴール","player",p.getName()));
        Bukkit.broadcastMessage("§6§l山頂ゴール！ §f"+p.getName()+" §a+"+win+" WIN");
        for(Player online:world.getPlayers()){online.sendTitle("§6§lGOAL!","§f+"+win+" WIN",5,70,15);online.playSound(online,Sound.UI_TOAST_CHALLENGE_COMPLETE,1,1);}
        getServer().getScheduler().runTaskLater(this,()->{resetPlayers();active=true;},100);
    }
    private void resetPlayers(){
        checkpoints.clear();checkpointLevels.clear();goalHold.clear();clearMobs();
        for(Player p:world.getPlayers()){p.leaveVehicle();p.teleport(start);p.setFallDistance(0);p.setInvulnerable(false);p.setGlowing(false);invulnerableUntil.remove(p.getUniqueId());}
    }
    private void clearMobs(){
        for(UUID id:new HashSet<>(gameMobs)){Entity e=Bukkit.getEntity(id);if(e!=null)e.remove();}gameMobs.clear();
        for(UUID id:new HashSet<>(vehicles)){Entity e=Bukkit.getEntity(id);if(e!=null)e.remove();}vehicles.clear();
    }
    private void give(Player p,Material material,int amount,String name){
        ItemStack item=new ItemStack(material,Math.max(1,Math.min(64,amount)));var meta=item.getItemMeta();meta.setDisplayName(name);item.setItemMeta(meta);p.getInventory().addItem(item);
    }
    private String gunName(String type){return switch(type){case "handgun"->"§fハンドガン";case "smg"->"§bマシンガン";case "rifle"->"§aアサルトライフル";default->"§cRPG";};}
    private Material gunMaterial(String type){return switch(type){case "handgun"->Material.IRON_HOE;case "smg"->Material.GOLDEN_HOE;case "rifle"->Material.DIAMOND_HOE;default->Material.NETHERITE_HOE;};}
    private ItemStack findGun(Player p,String type){
        for(ItemStack item:p.getInventory().getContents())if(item!=null&&item.hasItemMeta()&&type.equals(item.getItemMeta().getPersistentDataContainer().get(gunTypeKey,PersistentDataType.STRING)))return item;
        return null;
    }
    private void refreshGun(ItemStack item){
        if(item==null||!item.hasItemMeta())return;ItemMeta meta=item.getItemMeta();var data=meta.getPersistentDataContainer();
        String type=data.get(gunTypeKey,PersistentDataType.STRING);Integer ammo=data.get(gunAmmoKey,PersistentDataType.INTEGER);Integer mag=data.get(gunMagazineKey,PersistentDataType.INTEGER);Integer used=data.get(gunUsedKey,PersistentDataType.INTEGER);
        if(type==null)return;meta.setDisplayName(gunName(type));meta.setLore(List.of("§e残弾: §f"+Math.max(0,ammo==null?0:ammo),"§7マガジン: "+Math.max(0,(mag==null?1:mag)-(used==null?0:used))+"/"+(mag==null?1:mag),"§8右クリックで発射"));item.setItemMeta(meta);
    }
    private void giveGun(Player p,String type,int ammo,double damage,long intervalMs,int magazine,long reloadMs){
        ItemStack item=findGun(p,type);if(item==null){item=new ItemStack(gunMaterial(type));ItemMeta m=item.getItemMeta();m.getPersistentDataContainer().set(gunTypeKey,PersistentDataType.STRING,type);m.getPersistentDataContainer().set(gunUsedKey,PersistentDataType.INTEGER,0);item.setItemMeta(m);p.getInventory().addItem(item);}
        ItemMeta meta=item.getItemMeta();var data=meta.getPersistentDataContainer();Integer current=data.get(gunAmmoKey,PersistentDataType.INTEGER);
        data.set(gunAmmoKey,PersistentDataType.INTEGER,Math.max(0,current==null?0:current)+Math.max(1,ammo));data.set(gunDamageKey,PersistentDataType.DOUBLE,Math.max(.1,damage));data.set(gunIntervalKey,PersistentDataType.LONG,Math.max(0,intervalMs));data.set(gunMagazineKey,PersistentDataType.INTEGER,Math.max(1,magazine));data.set(gunReloadKey,PersistentDataType.LONG,Math.max(0,reloadMs));item.setItemMeta(meta);refreshGun(item);
        p.sendMessage("§a"+gunName(type)+" §f弾薬 +"+Math.max(1,ammo));
    }
    private void beginReload(Player p,ItemStack item,long reloadMs){
        UUID id=p.getUniqueId();long until=System.currentTimeMillis()+reloadMs;gunReloadUntil.put(id,until);p.sendMessage("§eリロード中…");
        getServer().getScheduler().runTaskLater(this,()->{if(gunReloadUntil.getOrDefault(id,0L)<=System.currentTimeMillis()){gunReloadUntil.remove(id);if(item.hasItemMeta()){ItemMeta m=item.getItemMeta();m.getPersistentDataContainer().set(gunUsedKey,PersistentDataType.INTEGER,0);item.setItemMeta(m);refreshGun(item);}p.playSound(p,Sound.BLOCK_IRON_TRAPDOOR_CLOSE,.8f,1.4f);p.sendMessage("§aリロード完了");}},Math.max(1,reloadMs/50));
    }
    private void shield(Player p,int seconds){
        UUID id=p.getUniqueId();long until=Math.max(invulnerableUntil.getOrDefault(id,0L),System.currentTimeMillis()+Math.max(1,seconds)*1000L);invulnerableUntil.put(id,until);p.setInvulnerable(true);p.setGlowing(true);
        getServer().getScheduler().runTaskLater(this,()->{if(invulnerableUntil.getOrDefault(id,0L)<=System.currentTimeMillis()){invulnerableUntil.remove(id);p.setInvulnerable(false);p.setGlowing(false);}},Math.max(1,seconds)*20L+1);
    }
    private void spawnMob(Player p,EntityType type,int count){
        for(int i=0;i<Math.min(100,count);i++){
            Location at=p.getLocation().add((Math.random()-.5)*10,2+(Math.random()*3),(Math.random()-.5)*10);
            Entity e=world.spawnEntity(at,type);gameMobs.add(e.getUniqueId());
            if(e instanceof Mob mob)mob.setTarget(p);
        }
    }
    private void cage(Player p,int seconds){
        Location c=p.getLocation().getBlock().getLocation();List<Block> changed=new ArrayList<>();
        for(int x=-1;x<=1;x++)for(int y=0;y<=2;y++)for(int z=-1;z<=1;z++)if(Math.abs(x)==1||Math.abs(z)==1||y==2){Block b=c.getBlock().getRelative(x,y,z);if(b.isEmpty()){b.setType(Material.BARRIER,false);changed.add(b);}}
        getServer().getScheduler().runTaskLater(this,()->changed.forEach(b->{if(b.getType()==Material.BARRIER)b.setType(Material.AIR,false);}),Math.max(1,seconds)*20L);
    }
    private void obstacle(Player p,int seconds){
        Location c=p.getLocation().add(p.getLocation().getDirection().setY(0).normalize().multiply(4)).getBlock().getLocation();List<Block> changed=new ArrayList<>();
        for(int x=-2;x<=2;x++)for(int y=0;y<4;y++){Block b=world.getBlockAt(c.getBlockX()+x,c.getBlockY()+y,c.getBlockZ());if(b.isEmpty()){b.setType(Material.RED_STAINED_GLASS,false);changed.add(b);}}
        getServer().getScheduler().runTaskLater(this,()->changed.forEach(b->{if(b.getType()==Material.RED_STAINED_GLASS)b.setType(Material.AIR,false);}),Math.max(1,seconds)*20L);
    }
    private void vehicle(Player p,String type){
        Pig pig=(Pig)world.spawnEntity(p.getLocation(),EntityType.PIG);pig.setSaddle(true);pig.setInvisible(true);pig.setInvulnerable(true);
        var attr=pig.getAttribute(Attribute.GENERIC_MOVEMENT_SPEED);if(attr!=null)attr.setBaseValue(type.equals("bike")?.42:.32);
        pig.setCustomName(type.equals("bike")?"バイク":"車");
        BlockDisplay body=(BlockDisplay)world.spawnEntity(p.getLocation(),EntityType.BLOCK_DISPLAY);body.setBlock((type.equals("bike")?Material.BLACK_CONCRETE:Material.RED_CONCRETE).createBlockData());pig.addPassenger(body);pig.addPassenger(p);
        vehicles.add(pig.getUniqueId());vehicles.add(body.getUniqueId());p.getInventory().addItem(new ItemStack(Material.CARROT_ON_A_STICK));
    }
    private void effect(String[] a){
        if(a.length<2)throw new IllegalArgumentException("effect type [amount] [player]");
        String kind=a[1];int amount=a.length>2?Integer.parseInt(a[2]):1;Player p=target(null);if(p==null)throw new IllegalArgumentException("Player not found");
        switch(kind){
            case "tnt"->{for(int i=0;i<Math.min(128,amount);i++){TNTPrimed t=world.spawn(p.getLocation().add((Math.random()-.5)*12,8+Math.random()*6,(Math.random()-.5)*12),TNTPrimed.class);t.setFuseTicks(50);}}
            case "zombie"->spawnMob(p,EntityType.ZOMBIE,amount);
            case "creeper"->spawnMob(p,EntityType.CREEPER,amount);
            case "launch"->p.setVelocity(new Vector(0,Math.max(.5,amount/2.0),0));
            case "freeze"->cage(p,amount);
            case "darkness"->p.addPotionEffect(new PotionEffect(PotionEffectType.DARKNESS,amount*20,1));
            case "lightning"->{world.strikeLightningEffect(p.getLocation());p.damage(Math.max(1,amount));}
            case "reset"->p.teleport(start);
            case "checkpoint"->p.teleport(checkpoints.getOrDefault(p.getUniqueId(),start));
            case "shield"->shield(p,amount);
            case "speed"->p.addPotionEffect(new PotionEffect(PotionEffectType.SPEED,amount*20,2));
            case "jump"->p.addPotionEffect(new PotionEffect(PotionEffectType.JUMP_BOOST,amount*20,2));
            case "boost"->p.setVelocity(p.getLocation().getDirection().normalize().multiply(Math.max(1,amount)).setY(.5));
            case "clear_mobs"->clearMobs();
            case "obstacle"->obstacle(p,amount);
            case "car","bike"->vehicle(p,kind);
            case "sword"->give(p,Material.DIAMOND_SWORD,1,"§b救済の剣");
            case "bow"->{give(p,Material.BOW,1,"§a救済の弓");give(p,Material.ARROW,Math.max(1,amount),"§f矢");}
            case "heal"->{p.setHealth(Math.min(p.getMaxHealth(),p.getHealth()+Math.max(1,amount)));p.playSound(p,Sound.ENTITY_PLAYER_LEVELUP,.8f,1.5f);}
            case "clear_inventory"->{p.getInventory().clear();gunCooldown.remove(p.getUniqueId());gunReloadUntil.remove(p.getUniqueId());p.sendMessage("§c持ち物をすべて失いました");}
            case "guide"->give(p,Material.COMPASS,1,"§6山頂コンパス");
            case "boss"->spawnMob(p,EntityType.RAVAGER,amount);
            case "armed_villager"->spawnMob(p,EntityType.PILLAGER,amount);
            case "gun_handgun","gun_smg","gun_rifle","gun_rpg"->{String type=kind.substring(4);double damage=a.length>3?Double.parseDouble(a[3]):(type.equals("handgun")?5:3);long interval=a.length>4?Long.parseLong(a[4]):300;int magazine=a.length>5?Integer.parseInt(a[5]):12;long reload=a.length>6?Long.parseLong(a[6]):1500;giveGun(p,type,amount,damage,interval,magazine,reload);}
            default->throw new IllegalArgumentException("Unknown effect");
        }
    }
    @Override public boolean onCommand(CommandSender sender,Command command,String label,String[] a){
        if(sender instanceof Player){sender.sendMessage("Console only");return true;}
        try{
            if(a.length==0||a[0].equals("status")){
                List<Map<String,Object>> players=new ArrayList<>();
                if(world!=null)for(Player p:world.getPlayers()){
                    Location cp=checkpoints.getOrDefault(p.getUniqueId(),start);
                    double distance=goal==null?0:p.getLocation().distance(goal);
                    Location here=p.getLocation();players.add(Map.of("name",p.getName(),"x",here.getX(),"y",here.getY(),"z",here.getZ(),
                            "checkpointY",cp==null?here.getY():cp.getY(),"distanceToGoal",distance));
                }
                Map<String,Object> state=new LinkedHashMap<>();state.put("ok",true);state.put("active",active);
                state.put("world",world==null?"":world.getName());state.put("players",players);state.put("wins",wins);
                sender.sendMessage(json.toJson(state));return true;
            }
            if(a[0].equals("ack")){if(a.length>1)wins.removeIf(w->Objects.equals(w.get("eventId"),a[1]));}
            else if(a[0].equals("configure")){
                if(a.length<11)throw new IllegalArgumentException("configure world sx sy sz gx gy gz radius checkpoint win [hold] [checkpoint] [deathMinus] [guide]");
                world=Bukkit.getWorld(a[1]);if(world==null)throw new IllegalArgumentException("World not found");
                start=new Location(world,Double.parseDouble(a[2]),Double.parseDouble(a[3]),Double.parseDouble(a[4]));goal=new Location(world,Double.parseDouble(a[5]),Double.parseDouble(a[6]),Double.parseDouble(a[7]));goalRadius=Double.parseDouble(a[8]);checkpointRise=Integer.parseInt(a[9]);win=Integer.parseInt(a[10]);goalHoldSeconds=a.length>11?Integer.parseInt(a[11]):5;checkpointsEnabled=a.length>12?Boolean.parseBoolean(a[12]):true;deathMinusWin=a.length>13&&Boolean.parseBoolean(a[13]);guideEnabled=a.length<=14||Boolean.parseBoolean(a[14]);
                getConfig().set("world",world.getName());storeLocation("start",start);storeLocation("goal",goal);getConfig().set("goalRadius",goalRadius);getConfig().set("checkpointRise",checkpointRise);getConfig().set("win",win);getConfig().set("goalHoldSeconds",goalHoldSeconds);getConfig().set("checkpointsEnabled",checkpointsEnabled);getConfig().set("deathMinusWin",deathMinusWin);getConfig().set("guideEnabled",guideEnabled);saveConfig();active=true;resetPlayers();
            } else if(a[0].equals("effect"))effect(a);
            else if(a[0].equals("reset")){resetPlayers();active=true;}
            else if(a[0].equals("environment")){daylight=Boolean.parseBoolean(a[1]);clearWeather=Boolean.parseBoolean(a[2]);}
            else throw new IllegalArgumentException("Unknown command");
            sender.sendMessage(json.toJson(Map.of("ok",true)));
        }catch(Exception ex){sender.sendMessage(json.toJson(Map.of("ok",false,"message",String.valueOf(ex.getMessage()))));}
        return true;
    }

    // The course is immutable. Explosions still hurt entities but never remove terrain.
    @EventHandler(priority=EventPriority.HIGHEST) public void breakBlock(BlockBreakEvent e){e.setCancelled(true);}
    @EventHandler(priority=EventPriority.HIGHEST) public void placeBlock(BlockPlaceEvent e){e.setCancelled(true);}
    @EventHandler(priority=EventPriority.HIGHEST) public void entityExplode(EntityExplodeEvent e){e.blockList().clear();}
    @EventHandler(priority=EventPriority.HIGHEST) public void blockExplode(BlockExplodeEvent e){e.blockList().clear();}
    @EventHandler(priority=EventPriority.HIGHEST) public void burn(BlockBurnEvent e){e.setCancelled(true);}
    @EventHandler(priority=EventPriority.HIGHEST) public void fade(BlockFadeEvent e){e.setCancelled(true);}
    @EventHandler(priority=EventPriority.HIGHEST) public void piston(BlockPistonExtendEvent e){e.setCancelled(true);}
    @EventHandler(priority=EventPriority.HIGHEST) public void pistonBack(BlockPistonRetractEvent e){e.setCancelled(true);}
    @EventHandler(priority=EventPriority.HIGHEST) public void flow(BlockFromToEvent e){e.setCancelled(true);}
    @EventHandler public void playerDeath(PlayerDeathEvent e){e.setKeepInventory(true);e.setKeepLevel(true);e.getDrops().clear();if(deathMinusWin){wins.add(Map.of("eventId",UUID.randomUUID().toString(),"win",-1,"reason","プレイヤーデス","player",e.getEntity().getName()));Bukkit.broadcastMessage("§cデス：-1 WIN");}}
    @EventHandler public void death(PlayerRespawnEvent e){if(start!=null)getServer().getScheduler().runTask(this,()->e.getPlayer().teleport(checkpointsEnabled?checkpoints.getOrDefault(e.getPlayer().getUniqueId(),start):start));}
    @EventHandler public void useGun(PlayerInteractEvent e){
        if(e.getHand()!=EquipmentSlot.HAND||(e.getAction()!=Action.RIGHT_CLICK_AIR&&e.getAction()!=Action.RIGHT_CLICK_BLOCK))return;ItemStack item=e.getItem();if(item==null||!item.hasItemMeta())return;
        ItemMeta meta=item.getItemMeta();var data=meta.getPersistentDataContainer();String type=data.get(gunTypeKey,PersistentDataType.STRING);if(type==null)return;e.setCancelled(true);Player p=e.getPlayer();UUID id=p.getUniqueId();long now=System.currentTimeMillis();
        if(gunReloadUntil.getOrDefault(id,0L)>now){p.sendActionBar("§eリロード中…");return;}long interval=Optional.ofNullable(data.get(gunIntervalKey,PersistentDataType.LONG)).orElse(300L);if(gunCooldown.getOrDefault(id,0L)>now)return;gunCooldown.put(id,now+interval);
        int ammo=Optional.ofNullable(data.get(gunAmmoKey,PersistentDataType.INTEGER)).orElse(0),magazine=Optional.ofNullable(data.get(gunMagazineKey,PersistentDataType.INTEGER)).orElse(1),used=Optional.ofNullable(data.get(gunUsedKey,PersistentDataType.INTEGER)).orElse(0);long reload=Optional.ofNullable(data.get(gunReloadKey,PersistentDataType.LONG)).orElse(1500L);double damage=Optional.ofNullable(data.get(gunDamageKey,PersistentDataType.DOUBLE)).orElse(3d);
        if(ammo<=0){p.sendActionBar("§c弾切れ");p.playSound(p,Sound.BLOCK_DISPENSER_FAIL,.8f,1);return;}if(used>=magazine){beginReload(p,item,reload);return;}
        int burst=type.equals("smg")?5:type.equals("rifle")?3:1,shots=Math.min(burst,Math.min(ammo,magazine-used));
        for(int i=0;i<shots;i++)if(type.equals("rpg")){Fireball b=p.launchProjectile(Fireball.class);b.setYield(Math.max(1,Math.min(8,(float)(damage/4))));b.setIsIncendiary(false);projectileDamage.put(b.getUniqueId(),damage);}else{double spread=type.equals("handgun")?.02:.05;Arrow arrow=p.launchProjectile(Arrow.class,p.getLocation().getDirection().add(new Vector((Math.random()-.5)*spread,(Math.random()-.5)*spread,(Math.random()-.5)*spread)).multiply(type.equals("handgun")?3.2:4));arrow.setDamage(damage);arrow.setPickupStatus(AbstractArrow.PickupStatus.DISALLOWED);projectileDamage.put(arrow.getUniqueId(),damage);}
        data.set(gunAmmoKey,PersistentDataType.INTEGER,ammo-shots);data.set(gunUsedKey,PersistentDataType.INTEGER,used+shots);item.setItemMeta(meta);refreshGun(item);p.playSound(p,type.equals("rpg")?Sound.ENTITY_GENERIC_EXPLODE:Sound.ENTITY_FIREWORK_ROCKET_BLAST,.8f,type.equals("smg")?1.8f:1.2f);
        if(used+shots>=magazine&&ammo-shots>0)beginReload(p,item,reload);
    }
    @EventHandler public void projectileHit(EntityDamageByEntityEvent e){Double damage=projectileDamage.remove(e.getDamager().getUniqueId());if(damage!=null)e.setDamage(damage);}
    @EventHandler public void join(PlayerJoinEvent e){if(active)getServer().getScheduler().runTaskLater(this,()->e.getPlayer().teleport(start),10);}
}
