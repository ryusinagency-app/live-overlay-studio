package studio.liveminecraft;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import java.util.*;
import org.bukkit.*;
import org.bukkit.block.Block;
import org.bukkit.command.*;
import org.bukkit.entity.Player;
import org.bukkit.entity.TNTPrimed;
import org.bukkit.entity.BlockDisplay;
import org.bukkit.entity.Firework;
import org.bukkit.entity.Enderman;
import org.bukkit.entity.FallingBlock;
import org.bukkit.event.*;
import org.bukkit.event.block.*;
import org.bukkit.event.entity.*;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.inventory.meta.FireworkMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.scheduler.BukkitRunnable;
import org.bukkit.util.RayTraceResult;
import org.bukkit.util.Vector;
import org.bukkit.util.Transformation;
import org.bukkit.potion.PotionEffect;
import org.bukkit.potion.PotionEffectType;
import org.joml.Quaternionf;
import org.joml.Vector3f;
import java.nio.charset.StandardCharsets;
import org.bukkit.plugin.java.JavaPlugin;

/** All world reads, protection, effects and success decisions run on the server thread. */
public final class ArenaPlugin extends JavaPlugin implements Listener {
    private final Gson json = new Gson();
    private final BitSet filled = new BitSet();
    private final Round round = new Round();
    private final List<Map<String, Object>> wins = new ArrayList<>();
    private final Deque<Runnable> edits = new ArrayDeque<>();
    private Bounds bounds;
    private World world;
    private Material frame = Material.GLASS, fill = Material.DIAMOND_BLOCK;
    private int hold = 10, win = 1, shield = 0, rounds = 0, cursor = 0;
    private long tick = 0, sweep = 0, fullSweep = -1;
    private boolean clear = true, ready = false, started = false;
    private boolean topLayerWin = false, gravityFill = false;
    private boolean floorEnabled = false;
    private boolean daylightFixed = true, clearWeather = true;
    private int floorMax = 100, floorHealth = 100, floorDamage = 10, floorPenalty = 1;
    private final Random random = new Random();
    private int minWidth = 3, maxWidth = 64, minHeight = 3, maxHeight = 64;
    private int bombs = 0, chains = 0, spread = 27;
    private String successText = "WIN！";
    private long generation = 0, announcementUntil = 0;
    private String resizeRevision = UUID.randomUUID().toString();
    private final Map<UUID, Long> frozen = new HashMap<>();
    private NamespacedKey itemKey;

    @Override public void onEnable() {
        getServer().getPluginManager().registerEvents(this, this);
        itemKey = new NamespacedKey(this, "special-item");
        bombs = getConfig().getInt("bombs", 0); chains = getConfig().getInt("chains", 0); spread = getConfig().getInt("spread", 27);
        successText = getConfig().getString("successText", "WIN！");
        daylightFixed = getConfig().getBoolean("daylightFixed", true);
        clearWeather = getConfig().getBoolean("clearWeather", true);
        Objects.requireNonNull(getCommand("lmsarena")).setExecutor(this);
        String pending = getConfig().getString("pendingWins", "[]");
        List<Map<String, Object>> restored = json.fromJson(pending, new TypeToken<List<Map<String, Object>>>(){}.getType());
        if (restored != null) wins.addAll(restored);
        // Keep an existing generated frame protected after a server restart.
        if (getConfig().contains("arena")) {
            try { configure(getConfig().getString("arena").split(" ")); }
            catch (Exception ex) { getLogger().warning("Saved arena could not be restored: " + ex.getMessage()); }
        }
        getServer().getScheduler().runTaskTimer(this, this::update, 1, 1);
    }

    private void saveWins() { getConfig().set("pendingWins", json.toJson(wins)); saveConfig(); }

    private boolean sameWorld(Block b) { return world != null && world.equals(b.getWorld()); }
    private boolean inside(Block b) { return bounds != null && sameWorld(b) && bounds.inside(b.getX(), b.getY(), b.getZ()); }
    private boolean protectedBlock(Block b) { return bounds != null && sameWorld(b) && (bounds.frame(b.getX(), b.getY(), b.getZ()) || b.getType()==Material.BARRIER); }
    private Block block(int i) { return world.getBlockAt(bounds.px(i), bounds.py(i), bounds.pz(i)); }
    private void changed(Block b) {
        if (!inside(b)) return;
        int i = bounds.index(b.getX(), b.getY(), b.getZ());
        boolean present = b.getType() == fill;
        if (filled.get(i) && !present) { round.lostBlock(); fullSweep = -1; }
        filled.set(i, present);
    }
    private void later(Block b) { getServer().getScheduler().runTask(this, () -> changed(b)); }

    private void configure(String[] a) {
        // configure world x y z width depth height frame fill hold win clear
        if (a.length != 17 && a.length != 21 && a.length != 23) throw new IllegalArgumentException("Invalid arena settings");
        Bounds oldBounds = bounds; World oldWorld = world; Material oldFill = fill;
        World next = Bukkit.getWorld(a[1]);
        if (next == null) throw new IllegalArgumentException("World not found: " + a[1]);
        Bounds b = new Bounds(Integer.parseInt(a[2]), Integer.parseInt(a[3]), Integer.parseInt(a[4]),
            Integer.parseInt(a[5]), Integer.parseInt(a[6]), Integer.parseInt(a[7]));
        if (b.width() < 3 || b.width() > 64 || b.depth() < 3 || b.depth() > 64 || b.height() < 3 || b.height() > 64
            || b.y() - 1 < next.getMinHeight() || b.y() + b.height() >= next.getMaxHeight()) throw new IllegalArgumentException("Arena is outside supported bounds");
        Material f = Material.matchMaterial(a[8]), v = Material.matchMaterial(a[9]);
        if (f == null || v == null || !f.isBlock() || !v.isBlock() || f.isAir() || v.isAir() || !v.isSolid()) throw new IllegalArgumentException("Invalid block material");
        int seconds = Integer.parseInt(a[10]), award = Integer.parseInt(a[11]);
        if (seconds < 1 || seconds > 3600 || award < 0 || award > 1000000) throw new IllegalArgumentException("Invalid countdown or WIN");
        int maximum = Integer.parseInt(a[14]), damage = Integer.parseInt(a[15]), penalty = Integer.parseInt(a[16]);
        if (maximum < 1 || maximum > 1000000 || damage < 1 || damage > 1000000 || penalty < 0 || penalty > 1000000) throw new IllegalArgumentException("Invalid floor settings");
        int minW = a.length >= 21 ? Integer.parseInt(a[17]) : 3, maxW = a.length >= 21 ? Integer.parseInt(a[18]) : 64;
        int minH = a.length >= 21 ? Integer.parseInt(a[19]) : 3, maxH = a.length >= 21 ? Integer.parseInt(a[20]) : 64;
        if (minW < 3 || maxW > 64 || minW > maxW || minH < 3 || maxH > 64 || minH > maxH) throw new IllegalArgumentException("Invalid size limits (3-64)");
        world = next; bounds = b; frame = f; fill = v; hold = seconds; win = award; clear = Boolean.parseBoolean(a[12]);
        floorEnabled = Boolean.parseBoolean(a[13]); floorMax = maximum; floorHealth = maximum; floorDamage = damage; floorPenalty = penalty;
        minWidth = minW; maxWidth = maxW; minHeight = minH; maxHeight = maxH; generation++; resizeRevision = UUID.randomUUID().toString();
        topLayerWin = a.length >= 23 && Boolean.parseBoolean(a[21]);
        gravityFill = a.length >= 23 && Boolean.parseBoolean(a[22]);
        edits.clear(); filled.clear(); cursor = 0; ready = false; started = true; shield = 0; round.reset(); fullSweep = -1;
        if (oldBounds != null && oldWorld != null) removeOldArena(oldWorld, oldBounds, b, oldFill);
    }

    private void removeOldArena(World oldWorld, Bounds old, Bounds replacement, Material previousFill) {
        for (int y=old.y()-1; y<old.y()+old.height(); y++)
            for (int z=old.z()-1; z<=old.z()+old.depth(); z++)
                for (int x=old.x()-1; x<=old.x()+old.width(); x++)
                    if ((old.frame(x,y,z) && (!oldWorld.equals(world) || !replacement.frame(x,y,z))) ||
                        (old.inside(x,y,z) && (!oldWorld.equals(world) || !replacement.inside(x,y,z)) &&
                         oldWorld.getBlockAt(x,y,z).getType()==previousFill)) {
                        Block target=oldWorld.getBlockAt(x,y,z);
                        edits.add(() -> target.setType(Material.AIR,false));
                    }
    }

    private void build() {
        // Bottom and four solid walls; no top face. Remove only a matching legacy roof.
        ready = false; round.reset(); fullSweep = -1;
        Bounds b = bounds;
        for (int y = b.y() - 1; y < b.y() + b.height(); y++)
            for (int z = b.z() - 1; z <= b.z() + b.depth(); z++)
                for (int x = b.x() - 1; x <= b.x() + b.width(); x++) {
                    if (b.frame(x, y, z)) {
                        final Block target = world.getBlockAt(x, y, z);
                        edits.add(() -> target.setType(frame, false));
                    }
                }
        for (int z = b.z() - 1; z <= b.z() + b.depth(); z++)
            for (int x = b.x() - 1; x <= b.x() + b.width(); x++) {
                final Block roof = world.getBlockAt(x, b.y() + b.height(), z);
                edits.add(() -> roof.setType(Material.AIR, false));
            }
        clearInterior();
    }

    private void clearInterior() {
        round.reset(); fullSweep = -1;
        for (int i = 0; i < bounds.capacity(); i++) {
            final int pos = i;
            edits.add(() -> { block(pos).setType(Material.AIR, false); filled.clear(pos); });
        }
    }
    private void fillSome(int amount, boolean remove) {
        for (int i = 0; i < bounds.capacity() && amount > 0; i++) {
            Block b = block(i);
            if (remove ? b.getType() == fill : b.getType() != fill) {
                final Block target = b;
                edits.add(() -> { target.setType(remove ? Material.AIR : fill, false); changed(target); });
                amount--;
            }
        }
    }

    private void fillLayers(int layers) {
        int remaining = Math.clamp(layers, 0, bounds.height());
        int layerSize = bounds.width() * bounds.depth();
        for (int layer = 0; layer < bounds.height() && remaining > 0; layer++) {
            int start = layer * layerSize;
            boolean incomplete = false;
            for (int i = start; i < start + layerSize; i++) {
                if (block(i).getType() != fill) { incomplete = true; break; }
            }
            if (!incomplete) continue;
            for (int i = start; i < start + layerSize; i++) {
                Block b = block(i);
                if (b.getType() != fill) {
                    final Block target = b;
                    edits.add(() -> { target.setType(fill, false); changed(target); });
                }
            }
            remaining--;
        }
    }

    private void fillByPercent(int percent) {
        int amount = (int)Math.ceil(bounds.capacity() * Math.clamp(percent, 0, 100) / 100.0);
        fillSome(amount, false);
    }

    private void evacuateInterior() {
        Location safe = new Location(world, bounds.x() + bounds.width() / 2.0 + .5,
            bounds.y() + bounds.height() + 1.0, bounds.z() + bounds.depth() / 2.0 + .5);
        for (Player p : world.getPlayers()) {
            Location at = p.getLocation();
            if (bounds.inside(at.getBlockX(), at.getBlockY(), at.getBlockZ())) {
                Location destination = safe.clone();
                destination.setYaw(at.getYaw()); destination.setPitch(at.getPitch());
                p.teleport(destination); p.setFallDistance(0);
            }
        }
    }

    private void celebration(boolean filling) {
        Color primary = filling ? Color.LIME : Color.RED;
        Color fade = filling ? Color.AQUA : Color.ORANGE;
        int[][] points = {{1,1},{Math.max(1,bounds.width()-2),1},{bounds.width()/2,Math.max(1,bounds.depth()-2)}};
        for (int[] point : points) {
            Location at = new Location(world, bounds.x()+point[0]+.5, bounds.y()+bounds.height()+2, bounds.z()+point[1]+.5);
            Firework firework = world.spawn(at, Firework.class);
            firework.addScoreboardTag("lms-celebration");
            FireworkMeta meta = firework.getFireworkMeta();
            meta.addEffect(FireworkEffect.builder().with(FireworkEffect.Type.BALL_LARGE).withColor(primary).withFade(fade).flicker(true).trail(true).build());
            meta.setPower(1); firework.setFireworkMeta(meta);
        }
        world.playSound(new Location(world,bounds.x()+bounds.width()/2.0,bounds.y()+bounds.height(),bounds.z()+bounds.depth()/2.0),
            filling ? Sound.ENTITY_PLAYER_LEVELUP : Sound.ENTITY_GENERIC_EXPLODE, 1, filling ? 1.2f : .8f);
    }

    private void fillAll(boolean effects) {
        evacuateInterior();
        fillSome(bounds.capacity(), false);
        if (effects) celebration(true);
    }

    private void clearAll(boolean effects) {
        clearInterior();
        if (effects) celebration(false);
    }

    private void saveArenaToken(int index, String value) {
        String[] saved = getConfig().getString("arena").split(" ");
        saved[index] = value; getConfig().set("arena", String.join(" ", saved)); saveConfig();
    }

    private void settings(String[] a) {
        if (a.length != 12 && a.length != 14) throw new IllegalArgumentException("Invalid live settings");
        int nextHold = Integer.parseInt(a[1]), nextWin = Integer.parseInt(a[2]);
        int maximum = Integer.parseInt(a[5]), damage = Integer.parseInt(a[6]), penalty = Integer.parseInt(a[7]);
        int minW = Integer.parseInt(a[8]), maxW = Integer.parseInt(a[9]), minH = Integer.parseInt(a[10]), maxH = Integer.parseInt(a[11]);
        if (nextHold < 1 || nextHold > 3600 || nextWin < 0 || maximum < 1 || maximum > 1000000 || damage < 1 || penalty < 0
            || minW < 3 || minW > maxW || maxW > 64 || minH < 3 || minH > maxH || maxH > 64) throw new IllegalArgumentException("Invalid live settings range");
        round.rebase(tick,hold,nextHold); hold = nextHold; win = nextWin; clear = Boolean.parseBoolean(a[3]); floorEnabled = Boolean.parseBoolean(a[4]);
        floorHealth = Math.min(floorHealth,maximum); floorMax = maximum; floorDamage = damage; floorPenalty = penalty;
        minWidth = minW; maxWidth = maxW; minHeight = minH; maxHeight = maxH;
        if (a.length >= 14) { topLayerWin=Boolean.parseBoolean(a[12]); gravityFill=Boolean.parseBoolean(a[13]); }
        String[] saved = Arrays.copyOf(getConfig().getString("arena").split(" "),23);
        if (saved[21] == null) saved[21] = "false";
        if (saved[22] == null) saved[22] = "false";
        System.arraycopy(a,1,saved,10,a.length-1); getConfig().set("arena",String.join(" ",saved)); saveConfig();
    }

    private void resize(String axis, int delta) {
        Bounds old = bounds;
        boolean horizontal = axis.equals("horizontal") || axis.equals("both");
        boolean vertical = axis.equals("height") || axis.equals("both");
        int w = horizontal ? Math.clamp(old.width() + delta, minWidth, maxWidth) : old.width();
        int d = horizontal ? Math.clamp(old.depth() + delta, minWidth, maxWidth) : old.depth();
        int h = vertical ? Math.clamp(old.height() + delta, minHeight, maxHeight) : old.height();
        h = Math.min(h, world.getMaxHeight() - old.y() - 1);
        if (w == old.width() && d == old.depth() && h == old.height()) return;
        bounds = new Bounds(old.x(), old.y(), old.z(), w, d, h);
        generation++; resizeRevision = UUID.randomUUID().toString();
        edits.clear(); round.reset(); filled.clear(); cursor = 0; ready = false; fullSweep = -1;
        // Remove old shell and cropped contents, preserving the overlapping interior.
        for (int y = old.y() - 1; y < old.y() + old.height(); y++)
            for (int z = old.z() - 1; z <= old.z() + old.depth(); z++)
                for (int x = old.x() - 1; x <= old.x() + old.width(); x++) {
                    if ((old.frame(x,y,z) && !bounds.frame(x,y,z)) || (old.inside(x,y,z) && !bounds.inside(x,y,z) && !bounds.frame(x,y,z))) {
                        Block b = world.getBlockAt(x,y,z); edits.add(() -> b.setType(Material.AIR, false));
                    }
                }
        for (int y = bounds.y() - 1; y < bounds.y() + bounds.height(); y++)
            for (int z = bounds.z() - 1; z <= bounds.z() + bounds.depth(); z++)
                for (int x = bounds.x() - 1; x <= bounds.x() + bounds.width(); x++) {
                    if (bounds.frame(x,y,z)) { Block b = world.getBlockAt(x,y,z); edits.add(() -> b.setType(frame, false)); }
                    else if (bounds.inside(x,y,z) && !old.inside(x,y,z)) { Block b = world.getBlockAt(x,y,z); edits.add(() -> b.setType(Material.AIR, false)); }
                }
        saveArenaToken(5, String.valueOf(w)); saveArenaToken(6, String.valueOf(d)); saveArenaToken(7, String.valueOf(h));
    }

    private void saveItems() { getConfig().set("bombs", bombs); getConfig().set("chains", chains); getConfig().set("spread", spread); saveConfig(); }
    private String special(ItemStack item) {
        if (item == null || !item.hasItemMeta()) return "";
        return item.getItemMeta().getPersistentDataContainer().getOrDefault(itemKey, PersistentDataType.STRING, "");
    }
    private void giveItem(Player p, String type) {
        for (ItemStack item : p.getInventory().getContents()) if (special(item).equals(type)) return;
        ItemStack item = new ItemStack(type.equals("bomb") ? Material.FIRE_CHARGE : fill);
        ItemMeta meta = item.getItemMeta();
        meta.setDisplayName(type.equals("bomb") ? "§6全埋めボム（右クリック）" : "§d連鎖ブロック（右クリック）");
        meta.getPersistentDataContainer().set(itemKey, PersistentDataType.STRING, type); item.setItemMeta(meta);
        int slot = -1;
        for (int i = 8; i >= 0; i--) {
            ItemStack current = p.getInventory().getItem(i);
            if (current == null || current.getType().isAir()) { slot = i; break; }
        }
        if (slot < 0) {
            for (int i = 8; i >= 0; i--) if (special(p.getInventory().getItem(i)).isEmpty()) { slot = i; break; }
        }
        if (slot < 0) slot = 8;
        ItemStack displaced = p.getInventory().getItem(slot);
        p.getInventory().setItem(slot, item);
        if (displaced != null && !displaced.getType().isAir()) {
            for (ItemStack leftover : p.getInventory().addItem(displaced).values())
                world.dropItemNaturally(p.getLocation(), leftover);
        }
        p.updateInventory();
    }
    private void consumeSpecial(Player p) {
        p.getInventory().setItemInMainHand(new ItemStack(Material.AIR));
        p.updateInventory();
    }

    private void showGiantTnt(TNTPrimed tnt, int fuse) {
        BlockDisplay display = world.spawn(tnt.getLocation().clone().subtract(1,1,1), BlockDisplay.class);
        display.setBlock(Material.TNT.createBlockData());
        display.setTransformation(new Transformation(new Vector3f(), new Quaternionf(), new Vector3f(3,3,3), new Quaternionf()));
        display.addScoreboardTag("lms-giant-visual");
        new BukkitRunnable() {
            int life = 0;
            public void run() {
                if (!tnt.isValid() || life++ > fuse + 10) { display.remove(); cancel(); return; }
                display.teleport(tnt.getLocation().clone().subtract(1,1,1));
            }
        }.runTaskTimer(this, 0, 1);
    }
    private void supplyItems() {
        if (world == null) return;
        for (Player p : world.getPlayers()) { if (bombs > 0) giveItem(p, "bomb"); if (chains > 0) giveItem(p, "chain"); }
    }
    private void chainFrom(Block start) {
        final long version = generation;
        final int limit = spread;
        Deque<Block> frontier = new ArrayDeque<>(); Set<String> seen = new HashSet<>();
        frontier.add(start);
        new BukkitRunnable() {
            int placed = 0;
            public void run() {
                if (version != generation || !edits.isEmpty()) { cancel(); return; }
                int attempts = 0;
                while (!frontier.isEmpty() && attempts++ < 64) {
                    Block b = frontier.removeFirst();
                    if (!inside(b) || !seen.add(b.getX()+","+b.getY()+","+b.getZ())) continue;
                    if (b.getType() != fill) { b.setType(fill, false); changed(b); placed++; }
                    frontier.add(b.getRelative(1,0,0)); frontier.add(b.getRelative(-1,0,0));
                    frontier.add(b.getRelative(0,1,0)); frontier.add(b.getRelative(0,-1,0));
                    frontier.add(b.getRelative(0,0,1)); frontier.add(b.getRelative(0,0,-1));
                    break;
                }
                if (placed >= limit || frontier.isEmpty()) cancel();
            }
        }.runTaskTimer(this, 0, 1);
    }

    private boolean topLayerComplete() {
        int y = bounds.y() + bounds.height() - 1;
        for (int z=bounds.z(); z<bounds.z()+bounds.depth(); z++)
            for (int x=bounds.x(); x<bounds.x()+bounds.width(); x++)
                if (world.getBlockAt(x,y,z).getType()!=fill) return false;
        return true;
    }

    private void rescueBuriedPlayers() {
        for (Player p : world.getPlayers()) {
            Location at=p.getLocation();
            if (!bounds.inside(at.getBlockX(),at.getBlockY(),at.getBlockZ())) continue;
            if (at.getBlock().getType()!=fill && at.clone().add(0,1,0).getBlock().getType()!=fill) continue;
            for (int y=Math.max(bounds.y(),at.getBlockY()+1); y<=bounds.y()+bounds.height()+2; y++) {
                Block feet=world.getBlockAt(at.getBlockX(),y,at.getBlockZ());
                Block head=world.getBlockAt(at.getBlockX(),y+1,at.getBlockZ());
                if (feet.isEmpty() && head.isEmpty()) {
                    Location safe=new Location(world,at.getBlockX()+.5,y,at.getBlockZ()+.5,at.getYaw(),at.getPitch());
                    p.teleport(safe); p.setFallDistance(0); break;
                }
            }
        }
    }

    private void dropFill(Block target) {
        if (!inside(target)) return;
        FallingBlock falling=world.spawnFallingBlock(target.getLocation().add(.5,.05,.5),fill.createBlockData());
        falling.setDropItem(false); falling.setCancelDrop(true); falling.addScoreboardTag("lms-fill");
    }

    private void update() {
        tick++;
        if (tick % 20 == 0) {
            supplyItems();
            if (world != null && daylightFixed) world.setTime(6000);
            if (world != null && clearWeather && (world.hasStorm() || world.isThundering())) {
                world.setStorm(false); world.setThundering(false); world.setWeatherDuration(0); world.setThunderDuration(0);
            }
        }
        if (!started || bounds == null) return;
        if (tick % 5 == 0) rescueBuriedPlayers();
        // Bound work per tick; event tracking provides immediate countdown cancellation.
        for (int n = 0; n < 2048 && !edits.isEmpty(); n++) edits.removeFirst().run();
        if (!edits.isEmpty()) return;
        int capacity = bounds.capacity();
        for (int n = 0; n < Math.min(4096, capacity); n++) {
            changed(block(cursor++));
            if (cursor >= capacity) { cursor = 0; sweep++; ready = true; }
        }
        if (!ready) return;
        boolean full = topLayerWin ? topLayerComplete() : filled.cardinality() == capacity;
        // Verify a complete sweep AFTER the countdown expires before granting a win.
        if (full && round.counting() && round.remaining(tick) == 0 && fullSweep < 0) fullSweep = sweep;
        if (!full) fullSweep = -1;
        if (round.tick(tick, full, hold, fullSweep >= 0 && sweep > fullSweep)) {
            rounds++;
            wins.add(Map.of("eventId", UUID.randomUUID().toString(), "win", win, "reason", "WIN"));
            saveWins();
            Bukkit.broadcastMessage("§aWIN！ +" + win);
            for (Player p : world.getPlayers()) {
                p.sendTitle("§a" + successText, "§f+" + win + " WIN", 2, 50, 10);
                p.playSound(p.getLocation(), Sound.UI_TOAST_CHALLENGE_COMPLETE, .9f, 1);
            }
            if (clear) clearInterior();
        }
        if (tick % 20 == 0 && tick >= announcementUntil && round.counting()) {
            long remaining = round.remaining(tick);
            if (remaining == 0) return;
            String title = "§e" + remaining;
            float pitch = remaining <= 3 ? 1.5f : 1.1f;
            for (Player p : world.getPlayers()) {
                p.sendTitle(title, "", 0, 22, 0);
                p.playSound(p.getLocation(), Sound.BLOCK_NOTE_BLOCK_HAT, .8f, pitch);
            }
        }
    }

    private Map<String, Object> state() {
        Map<String, Object> s = new LinkedHashMap<>();
        s.put("ok", true); s.put("protocol", 1); s.put("active", started); s.put("ready", ready && edits.isEmpty());
        s.put("filled", filled.cardinality()); s.put("capacity", bounds == null ? 0 : bounds.capacity());
        s.put("defending", round.counting()); s.put("holdRemainingSeconds", round.remaining(tick));
        s.put("shieldCharges", shield); s.put("completedRounds", rounds); s.put("wins", new ArrayList<>(wins));
        s.put("floorEnabled", floorEnabled); s.put("health", floorHealth); s.put("maxHealth", floorMax);
        s.put("bombCharges", bombs); s.put("chainCharges", chains); s.put("holdSeconds", hold);
        s.put("topLayerWin", topLayerWin); s.put("gravityFill", gravityFill);
        s.put("width", bounds == null ? 0 : bounds.width()); s.put("depth", bounds == null ? 0 : bounds.depth()); s.put("height", bounds == null ? 0 : bounds.height());
        s.put("resizeRevision", resizeRevision);
        return s;
    }

    private void cage(Player p, int seconds) {
        Location c=p.getLocation().getBlock().getLocation(); List<Block> placed=new ArrayList<>();
        for (int y=-1;y<=2;y++) for(int x=-1;x<=1;x++) for(int z=-1;z<=1;z++) {
            if (Math.abs(x)==1 || Math.abs(z)==1 || y==-1 || y==2) {
                Block b=c.clone().add(x,y,z).getBlock();
                if (b.isEmpty()) { b.setType(Material.BARRIER,false); placed.add(b); }
            }
        }
        p.teleport(c.clone().add(.5,.05,.5));
        long until=tick+seconds*20L; frozen.put(p.getUniqueId(),Math.max(until,frozen.getOrDefault(p.getUniqueId(),0L)));
        getServer().getScheduler().runTaskLater(this,()->placed.forEach(b->{if(b.getType()==Material.BARRIER)b.setType(Material.AIR,false);}),seconds*20L);
    }

    private void rocket(Player p, double strength) {
        boolean allowed=p.getAllowFlight(), flying=p.isFlying(); p.setFlying(false); p.setAllowFlight(false);
        TNTPrimed visual=world.spawn(p.getLocation(),TNTPrimed.class); visual.setFuseTicks(35); visual.setYield(0); visual.addScoreboardTag("lms-launch");
        p.setVelocity(new Vector(0,Math.max(1.2,strength),0));
        getServer().getScheduler().runTaskLater(this,()->{if(p.isOnline()){p.setAllowFlight(allowed);p.setFlying(flying&&allowed);}},45L);
    }

    private void endermanRaid(int amount) {
        List<Block> candidates=new ArrayList<>();
        for(int i=0;i<bounds.capacity();i++) if(block(i).getType()==fill)candidates.add(block(i));
        Collections.shuffle(candidates,random);
        for(int i=0;i<Math.min(amount,candidates.size());i++) {
            Block target=candidates.get(i); target.setType(Material.AIR,false); changed(target);
            Enderman mob=world.spawn(target.getLocation().add(.5,1,.5),Enderman.class);
            mob.setCarriedBlock(fill.createBlockData()); mob.addScoreboardTag("lms-enderman");
            getServer().getScheduler().runTaskLater(this,mob::remove,60L);
        }
    }

    private void spawnArenaTnt(String type, int fuse) {
        Location at=new Location(world,bounds.x()+.5+random.nextInt(bounds.width()),bounds.y()+bounds.height()+1.2,bounds.z()+.5+random.nextInt(bounds.depth()));
        TNTPrimed tnt=world.spawn(at,TNTPrimed.class); tnt.setVelocity(new Vector(0,0,0)); tnt.setFuseTicks(1200);
        tnt.setYield(type.equals("giant")?12f:3f); tnt.addScoreboardTag("lms-arena"); tnt.addScoreboardTag("lms-"+type);
        if(type.equals("giant"))showGiantTnt(tnt,1200);
        new BukkitRunnable(){public void run(){
            if(!tnt.isValid()){cancel();return;}
            Location here=tnt.getLocation();
            double x=Math.clamp(here.getX(),bounds.x()+.35,bounds.x()+bounds.width()-.35);
            double z=Math.clamp(here.getZ(),bounds.z()+.35,bounds.z()+bounds.depth()-.35);
            if(x!=here.getX() || z!=here.getZ()) tnt.teleport(new Location(world,x,here.getY(),z,here.getYaw(),here.getPitch()));
            Vector velocity=tnt.getVelocity(); tnt.setVelocity(new Vector(0,velocity.getY(),0));
            if(tnt.isOnGround() || tnt.getLocation().getY()<=bounds.y()+.05){tnt.setFuseTicks(fuse);cancel();}
        }}.runTaskTimer(this,1,1);
    }

    @Override public boolean onCommand(CommandSender sender, Command cmd, String label, String[] a) {
        if (!(sender instanceof ConsoleCommandSender) && !(sender instanceof RemoteConsoleCommandSender)) {
            sender.sendMessage("Server console only"); return true;
        }
        try {
            if (a.length == 0 || a[0].equals("status")) { sender.sendMessage(json.toJson(state())); return true; }
            if (a[0].equals("ack")) { wins.removeIf(w -> w.get("eventId").equals(a[1])); saveWins(); }
            else if (a[0].equals("configure") || a[0].equals("generate")) {
                boolean generate = a[0].equals("generate");
                a[0] = "configure"; configure(a); getConfig().set("arena", String.join(" ", a)); saveConfig();
                if (generate) build();
            }
            else {
                if (!started) throw new IllegalStateException("Generate the arena first");
                if (a[0].equals("build")) build();
                else if (a[0].equals("settings")) settings(a);
                else if (a[0].equals("fill")) fillSome(Math.max(0, Math.min(bounds.capacity(), Integer.parseInt(a[1]))), false);
                else if (a[0].equals("fill_all")) fillAll(true);
                else if (a[0].equals("fill_layers")) fillLayers(Integer.parseInt(a[1]));
                else if (a[0].equals("fill_percent")) fillByPercent(Integer.parseInt(a[1]));
                else if (a[0].equals("clear")) fillSome(Math.max(0, Math.min(bounds.capacity(), Integer.parseInt(a[1]))), true);
                else if (a[0].equals("clear_all")) clearAll(true);
                else if (a[0].equals("bomb")) { bombs = Math.min(1000000, bombs + Math.max(0, Integer.parseInt(a[1]))); saveItems(); supplyItems(); }
                else if (a[0].equals("chain")) { chains = Math.min(1000000, chains + Math.max(0, Integer.parseInt(a[1]))); spread = Math.clamp(Integer.parseInt(a[2]),1,10000); saveItems(); supplyItems(); }
                else if (a[0].equals("resize")) resize(a[1], Math.clamp(Integer.parseInt(a[2]), -64, 64));
                else if (a[0].equals("shield")) shield = Math.min(1000000, shield + Math.max(0, Integer.parseInt(a[1])));
                else if (a[0].equals("repair")) floorHealth = Math.min(floorMax, floorHealth + Math.max(0, Integer.parseInt(a[1])));
                else if (a[0].equals("countdown")) {
                    int next = Math.clamp(a[1].equals("set") ? Integer.parseInt(a[2]) : hold + Integer.parseInt(a[2]),1,3600);
                    round.rebase(tick, hold, next); hold = next; saveArenaToken(10, String.valueOf(hold));
                    resizeRevision = UUID.randomUUID().toString();
                }
                else if (a[0].equals("freeze")) {
                    int seconds=Math.clamp(Integer.parseInt(a[1]),1,600);
                    for (Player p : world.getPlayers()) cage(p,seconds);
                }
                else if (a[0].equals("launch")) {
                    double strength = Math.clamp(Double.parseDouble(a[1]), .1, 10);
                    for (Player p : world.getPlayers()) rocket(p,strength);
                }
                else if (a[0].equals("darkness")) {
                    int seconds=Math.clamp(Integer.parseInt(a[1]),1,600);
                    for(Player p:world.getPlayers())p.addPotionEffect(new PotionEffect(PotionEffectType.DARKNESS,seconds*20,0,false,false,true));
                }
                else if (a[0].equals("enderman")) endermanRaid(Math.clamp(Integer.parseInt(a[1]),1,256));
                else if (a[0].equals("announce")) {
                    Map<?,?> text = json.fromJson(new String(Base64.getDecoder().decode(a[1]), StandardCharsets.UTF_8), Map.class);
                    int duration = Math.clamp(((Number)text.get("duration")).intValue(),1,30);
                    announcementUntil = tick + duration * 20L;
                    for (Player p : world.getPlayers()) p.sendTitle(String.valueOf(text.get("text")), String.valueOf(text.get("sender")), 2,duration*20,5);
                }
                else if (a[0].equals("success_text")) {
                    successText = new String(Base64.getDecoder().decode(a[1]), StandardCharsets.UTF_8).trim();
                    if (successText.isEmpty()) successText = "WIN！";
                    if (successText.length() > 80) successText = successText.substring(0, 80);
                    getConfig().set("successText", successText); saveConfig();
                }
                else if (a[0].equals("environment")) {
                    daylightFixed = Boolean.parseBoolean(a[1]); clearWeather = Boolean.parseBoolean(a[2]);
                    getConfig().set("daylightFixed", daylightFixed); getConfig().set("clearWeather", clearWeather); saveConfig();
                    if (daylightFixed) world.setTime(6000);
                    if (clearWeather) { world.setStorm(false); world.setThundering(false); world.setWeatherDuration(0); world.setThunderDuration(0); }
                }
                else if (a[0].equals("tnt")) {
                    int count = Math.max(0, Math.min(256, Integer.parseInt(a[1])));
                    for (int i = 0; i < count; i++) {
                        String type = a.length > 2 ? a[2] : "normal";
                        int fuse = type.equals("timed") && a.length > 3 ? Math.clamp(Integer.parseInt(a[3]),20,1200) : 60;
                        spawnArenaTnt(type,fuse);
                    }
                } else throw new IllegalArgumentException("Unknown bridge command");
            }
            sender.sendMessage(json.toJson(Map.of("ok", true)));
        } catch (Exception ex) { sender.sendMessage(json.toJson(Map.of("ok", false, "message", String.valueOf(ex.getMessage())))); }
        return true;
    }

    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void protectBreak(BlockBreakEvent e) { if (protectedBlock(e.getBlock())) e.setCancelled(true); }
    @EventHandler(priority=EventPriority.MONITOR, ignoreCancelled=true)
    public void trackBreak(BlockBreakEvent e) {
        if (inside(e.getBlock()) && e.getBlock().getType() == fill) { round.lostBlock(); fullSweep = -1; later(e.getBlock()); }
    }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void protectPlace(BlockPlaceEvent e) {
        Block b = e.getBlock();
        if (protectedBlock(b) || aboveArena(b)) e.setCancelled(true);
        else if (inside(b) && gravityFill) {
            e.setCancelled(true);
            // Wait until Bukkit has rolled the cancelled placement back, otherwise
            // the falling entity can collide with the temporary placed block.
            getServer().getScheduler().runTask(this, () -> dropFill(b));
        }
        else if (inside(b)) b.setType(fill, false);
    }
    @EventHandler(priority=EventPriority.MONITOR, ignoreCancelled=true)
    public void trackPlace(BlockPlaceEvent e) { later(e.getBlock()); }

    private boolean aboveArena(Block b) {
        return bounds != null && sameWorld(b) && b.getX() >= bounds.x() - 1 && b.getX() <= bounds.x() + bounds.width()
            && b.getZ() >= bounds.z() - 1 && b.getZ() <= bounds.z() + bounds.depth() && b.getY() >= bounds.y() + bounds.height();
    }

    @EventHandler(priority=EventPriority.HIGHEST)
    public void remoteBreak(PlayerInteractEvent e) {
        if (!started || !ready || !edits.isEmpty() || e.getHand() != EquipmentSlot.HAND
            || (e.getAction() != Action.LEFT_CLICK_AIR && e.getAction() != Action.LEFT_CLICK_BLOCK)) return;
        Player p = e.getPlayer();
        if (!world.equals(p.getWorld()) || p.getGameMode() == GameMode.SPECTATOR
            || p.getGameMode() == GameMode.ADVENTURE) return;
        RayTraceResult hit = p.rayTraceBlocks(256, FluidCollisionMode.NEVER);
        if (hit == null || hit.getHitBlock() == null) return;
        Block target = hit.getHitBlock();
        if (!inside(target) || target.getType() != fill) return;
        e.setCancelled(true);
        target.setType(Material.AIR, false);
        changed(target);
        p.playSound(target.getLocation(), Sound.BLOCK_STONE_BREAK, .6f, 1);
    }

    @EventHandler(priority=EventPriority.HIGHEST)
    public void remotePlace(PlayerInteractEvent e) {
        if (!started || !ready || !edits.isEmpty() || e.getHand() != EquipmentSlot.HAND
            || (e.getAction() != Action.RIGHT_CLICK_AIR && e.getAction() != Action.RIGHT_CLICK_BLOCK)) return;
        Player p = e.getPlayer();
        ItemStack item = p.getInventory().getItemInMainHand();
        if (!world.equals(p.getWorld()) || p.getGameMode() == GameMode.SPECTATOR
            || p.getGameMode() == GameMode.ADVENTURE) return;
        String action = special(item);
        if (action.equals("bomb")) {
            e.setCancelled(true);
            if (bombs > 0 && filled.cardinality() < bounds.capacity()) { bombs--; saveItems(); consumeSpecial(p); fillAll(true); }
            else p.sendMessage("§e全埋めボムの残り: " + bombs);
            return;
        }
        if (!item.getType().isBlock() || item.getType().isAir()) return;
        // Bukkit marks air interactions cancelled by default; do not use ignoreCancelled here.
        RayTraceResult hit = p.rayTraceBlocks(256, FluidCollisionMode.NEVER);
        if (hit == null || hit.getHitBlock() == null || hit.getHitBlockFace() == null) return;
        Block base = hit.getHitBlock(), target = base.getRelative(hit.getHitBlockFace());
        if (!inside(base) && !protectedBlock(base) && !inside(target)) return;
        e.setCancelled(true); // Replace vanilla short-reach placement, including attempts above the rim.
        if (!inside(target) || (!target.isEmpty() && !target.isLiquid())) return;
        if (action.equals("chain")) {
            if (chains <= 0) { p.sendMessage("§e連鎖ブロックはギフトで補充できます"); return; }
            chains--; saveItems(); consumeSpecial(p); chainFrom(target); return;
        }
        if (gravityFill) dropFill(target);
        else { target.setType(fill, false); changed(target); }
        if (p.getGameMode() != GameMode.CREATIVE) {
            item.setAmount(item.getAmount() - 1);
            p.getInventory().setItemInMainHand(item);
        }
        // The arena always receives the configured fill material, but the feedback
        // should match the block the player actually chose to hold.
        Sound placeSound = Sound.BLOCK_STONE_PLACE;
        try { placeSound = item.getType().createBlockData().getSoundGroup().getPlaceSound(); }
        catch (RuntimeException ignored) { }
        p.playSound(target.getLocation(), placeSound, .8f, 1);
    }

    @EventHandler public void joined(PlayerJoinEvent e) { getServer().getScheduler().runTask(this, this::supplyItems); }
    @EventHandler(priority=EventPriority.HIGHEST,ignoreCancelled=true)
    public void move(PlayerMoveEvent e) {
        if (frozen.getOrDefault(e.getPlayer().getUniqueId(),0L) <= tick || e.getTo() == null) return;
        Location from = e.getFrom(), to = e.getTo();
        if (from.getX() != to.getX() || from.getY() != to.getY() || from.getZ() != to.getZ()) e.setTo(new Location(from.getWorld(),from.getX(),from.getY(),from.getZ(),to.getYaw(),to.getPitch()));
    }

    private void explosion(List<Block> blocks, boolean arenaTnt, boolean tnt, int damageFactor) {
        // Read exposure BEFORE destruction: the explosion removing the last bottom-layer
        // block cannot also damage the newly exposed floor in that same explosion.
        boolean floorHit = floorEnabled && tnt && blocks.stream().anyMatch(b -> sameWorld(b)
            && b.getY() == bounds.y() - 1 && b.getX() >= bounds.x() && b.getX() < bounds.x() + bounds.width()
            && b.getZ() >= bounds.z() && b.getZ() < bounds.z() + bounds.depth()
            && world.getBlockAt(b.getX(), bounds.y(), b.getZ()).isEmpty());
        blocks.removeIf(b -> protectedBlock(b) || (arenaTnt && !inside(b)));
        boolean affectsFill = blocks.stream().anyMatch(b -> inside(b) && b.getType() == fill);
        if ((affectsFill || floorHit) && shield > 0) { shield--; blocks.removeIf(this::inside); }
        else {
            if (affectsFill) { round.lostBlock(); fullSweep = -1; }
            if (floorHit) {
                floorHealth = Math.max(0, floorHealth - floorDamage * damageFactor);
                if (floorHealth == 0) {
                    wins.add(Map.of("eventId", UUID.randomUUID().toString(), "win", -floorPenalty, "reason", "底の耐久ゼロ"));
                    saveWins();
                    floorHealth = floorMax;
                    Bukkit.broadcastMessage("§c底の耐久ゼロ！ -" + floorPenalty + " WIN");
                }
            }
        }
        for (Block b : blocks) later(b);
    }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void entityExplosion(EntityExplodeEvent e) {
        if (bounds == null) return;
        Set<String> tags = e.getEntity().getScoreboardTags();
        if (tags.contains("lms-launch")) { e.blockList().clear(); return; }
        if (tags.contains("lms-piercing")) {
            e.blockList().clear(); int x = e.getLocation().getBlockX(), z = e.getLocation().getBlockZ();
            if (bounds.inside(x,bounds.y(),z)) for (int y = bounds.y()-1; y < bounds.y()+bounds.height(); y++) e.blockList().add(world.getBlockAt(x,y,z));
        }
        if (tags.contains("lms-arena") && !tags.contains("lms-piercing")) {
            Location center = e.getLocation();
            int radius = tags.contains("lms-giant") ? 10 : 3;
            for (int y = Math.max(bounds.y(),center.getBlockY()-radius); y < Math.min(bounds.y()+bounds.height(),center.getBlockY()+radius+1); y++)
                for (int z = Math.max(bounds.z(),center.getBlockZ()-radius); z < Math.min(bounds.z()+bounds.depth(),center.getBlockZ()+radius+1); z++)
                    for (int x = Math.max(bounds.x(),center.getBlockX()-radius); x < Math.min(bounds.x()+bounds.width(),center.getBlockX()+radius+1); x++) {
                        Block b = world.getBlockAt(x,y,z);
                        if (b.getLocation().add(.5,.5,.5).distanceSquared(center) <= radius*radius && !e.blockList().contains(b)) e.blockList().add(b);
                    }
            int floorX=Math.clamp(center.getBlockX(),bounds.x(),bounds.x()+bounds.width()-1);
            int floorZ=Math.clamp(center.getBlockZ(),bounds.z(),bounds.z()+bounds.depth()-1);
            if(center.getY()<=bounds.y()+1.2 && world.getBlockAt(floorX,bounds.y(),floorZ).isEmpty())
                e.blockList().add(world.getBlockAt(floorX,bounds.y()-1,floorZ));
        }
        explosion(e.blockList(), tags.contains("lms-arena"), e.getEntity() instanceof TNTPrimed, tags.contains("lms-giant") ? 8 : 1);
    }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void celebrationDamage(EntityDamageByEntityEvent e) {
        if (e.getDamager().getScoreboardTags().contains("lms-celebration")) e.setCancelled(true);
    }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void blockExplosion(BlockExplodeEvent e) { if (bounds != null) explosion(e.blockList(), false, false, 1); }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void burn(BlockBurnEvent e) { if (protectedBlock(e.getBlock())) e.setCancelled(true); }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void fade(BlockFadeEvent e) { if (protectedBlock(e.getBlock())) e.setCancelled(true); }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void entityChange(EntityChangeBlockEvent e) {
        if (e.getEntity().getScoreboardTags().contains("lms-fill")) {
            e.setCancelled(true);
            Block landing=e.getBlock();
            if (inside(landing)) { landing.setType(fill,false); changed(landing); }
            e.getEntity().remove(); return;
        }
        if (protectedBlock(e.getBlock())) e.setCancelled(true);
    }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void flow(BlockFromToEvent e) { if (protectedBlock(e.getToBlock())) e.setCancelled(true); }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void extend(BlockPistonExtendEvent e) {
        if (e.getBlocks().stream().anyMatch(b -> protectedBlock(b) || protectedBlock(b.getRelative(e.getDirection())))) e.setCancelled(true);
    }
    @EventHandler(priority=EventPriority.HIGHEST, ignoreCancelled=true)
    public void retract(BlockPistonRetractEvent e) {
        if (e.getBlocks().stream().anyMatch(b -> protectedBlock(b) || protectedBlock(b.getRelative(e.getDirection())))) e.setCancelled(true);
    }
}
