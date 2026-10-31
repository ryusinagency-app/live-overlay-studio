from __future__ import annotations

from copy import deepcopy
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Lock, Thread
import base64, json, mimetypes, os, queue, random, re, time, urllib.parse, urllib.request

from game_engine import Course, GameEngine, MultiplierState
from local_server import LocalMinecraftServer
from rcon import RconClient

APP_VERSION = "0.3.0"
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "LiveMinecraftMountainStudio"
SOUNDS_DIR, IMAGES_DIR = DATA_DIR / "sounds", DATA_DIR / "images"
for p in (DATA_DIR, SOUNDS_DIR, IMAGES_DIR): p.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "settings.json"
HOST, PORT = "127.0.0.1", 8776
LOCK = Lock()

CARD_STYLE = {"background":"#171b25","backgroundOpacity":88,"border":"#ef334e","text":"#ffffff","accent":"#54e694",
              "width":280,"height":190,"nameSize":22,"valueSize":25,"descriptionSize":14,"imageSize":64,
              "glowColor":"#ffd34e","outline":True,"outlineColor":"#000000","outlineWidth":3}
DEFAULT = {
 "rcon":{"host":"127.0.0.1","port":25576,"password":""},
 "course":{"world":"world","startX":0,"startY":64,"startZ":0,"goalX":0,"goalY":160,"goalZ":0,
           "goalRadius":4,"checkpointRise":20,"goalWin":1,"goalHoldSeconds":5,"checkpointsEnabled":True,"deathMinusWin":False,"guideEnabled":True,"hungerDisabled":True,"daylightFixed":True,"clearWeather":True},
 "winBridge":{"enabled":True,"url":"http://127.0.0.1:8765/api/minecraft-studio/win","token":""},
 "guns":{
   "handgun":{"giftAmmo":12,"damage":5,"intervalMs":450,"magazine":6,"reloadSeconds":1.5},
   "smg":{"giftAmmo":30,"damage":3,"intervalMs":180,"magazine":20,"reloadSeconds":2},
   "rifle":{"giftAmmo":24,"damage":4,"intervalMs":300,"magazine":12,"reloadSeconds":2.2},
   "rpg":{"giftAmmo":3,"damage":16,"intervalMs":1200,"magazine":1,"reloadSeconds":3}
 },
 "multiplier":{"enabled":True,"threshold":5000,"durationSeconds":300,"multiplier":2,
               "nextLabel":"次の倍率まで","startSoundUrl":"","startSoundVolume":100,"startSoundSeconds":0,
               "endSoundUrl":"","endSoundVolume":100,"endSoundSeconds":0},
 "effects":{},"gachas":{},"socialRuntime":{"followedUsers":[],"individualLikes":{},"totalLikes":0},
 "overlay":{"effectListStyle":deepcopy(CARD_STYLE),
            "courseStyle":{"background":"#080a0f","backgroundOpacity":84,"border":"#ef334e","text":"#ffffff","accent":"#54e694",
              "width":600,"titleSize":28,"textSize":18,"labelSize":18,"outline":True,"outlineColor":"#000000","outlineWidth":3},
            "feverStyle":{"background":"#111522","backgroundOpacity":88,"border":"#ffd34e","text":"#ffffff","accent":"#ffd34e",
              "width":520,"titleSize":30,"valueSize":40,"timerSize":34,"outline":True,"outlineColor":"#000000","outlineWidth":3},
            "gachaStyle":{"background":"#10131a","backgroundOpacity":92,"border":"#ef334e","text":"#ffffff","accent":"#ffd34e",
              "width":680,"nameSize":40,"senderSize":22,"reelSize":54,"resultSize":46,"imageSize":80,
              "outline":True,"outlineColor":"#000000","outlineWidth":3}},
}

def merge(base, loaded):
 result=deepcopy(base)
 for k,v in (loaded or {}).items():
  result[k]=merge(result[k],v) if isinstance(v,dict) and isinstance(result.get(k),dict) else v
 return result
try: STATE=merge(DEFAULT,json.loads(STATE_FILE.read_text("utf-8")))
except Exception: STATE=deepcopy(DEFAULT)

def make_engine():
 c,m=STATE["course"],STATE["multiplier"]
 return GameEngine(Course(c["world"],float(c["startX"]),float(c["startY"]),float(c["startZ"]),
  float(c["goalX"]),float(c["goalY"]),float(c["goalZ"]),float(c["goalRadius"]),int(c["checkpointRise"]),int(c["goalWin"]),int(c.get("goalHoldSeconds",5)),bool(c.get("checkpointsEnabled",True)),bool(c.get("deathMinusWin",False)),bool(c.get("guideEnabled",True)),bool(c.get("hungerDisabled",True))),
  MultiplierState(bool(m["enabled"]),int(m["threshold"]),int(m["durationSeconds"]),int(m["multiplier"])))
ENGINE=make_engine(); LOCAL=LocalMinecraftServer(DATA_DIR)
STATUS={"rcon":"未接続","lastError":"","lastSync":0,"wins":[]}
GACHA_EVENTS=[]; GACHA_QUEUE=queue.Queue()

def save(): STATE_FILE.write_text(json.dumps(STATE,ensure_ascii=False,indent=2),"utf-8")
def rcon(command):
 cfg=STATE["rcon"]
 with RconClient(cfg["host"],int(cfg["port"]),cfg["password"]) as client: raw=client.command(command)
 try: reply=json.loads(raw)
 except Exception: return raw
 if isinstance(reply,dict) and reply.get("ok") is False: raise RuntimeError(reply.get("message","Minecraft側で失敗しました"))
 return reply
def public_state():
 return {"version":APP_VERSION,"config":STATE,"game":ENGINE.snapshot(),"status":{**STATUS,"localServer":LOCAL.status()},
  "gachaEvents":list(GACHA_EVENTS[-60:]),"gachaQueueSize":GACHA_QUEUE.qsize(),"effectKinds":[
  ["tnt","TNTを降らせる"],["zombie","ゾンビ"],["creeper","クリーパー"],["launch","上へ吹き飛ばす"],
  ["freeze","牢屋へ閉じ込める"],["darkness","暗闇"],["lightning","雷"],["reset","スタートへ戻す"],
  ["checkpoint","チェックポイントへ救済"],["shield","無敵"],["speed","スピード"],["jump","ジャンプ力"],
  ["boost","前方ブースト"],["clear_mobs","敵を全消去"],["obstacle","障害物"],["car","車"],["bike","バイク"],
  ["sword","剣を付与"],["bow","弓矢を付与"],["heal","体力回復"],["clear_inventory","持ち物全ロスト"],["guide","山頂コンパス"],
  ["boss","ボス出現"],["gun_handgun","ハンドガン"],["gun_smg","マシンガン"],["gun_rifle","アサルトライフル"],["gun_rpg","RPG"],["armed_villager","武装村人"]]}

def send_win(event):
 cfg=STATE.get("winBridge",{})
 if not cfg.get("enabled",True): return True
 body=json.dumps({"amount":int(event.get("win",0)),"win":int(event.get("win",0)),"reason":event.get("reason","山登り"),"senderName":event.get("player",""),"source":"minecraft-mountain"},ensure_ascii=False).encode("utf-8")
 headers={"Content-Type":"application/json"}
 if cfg.get("token"): headers["X-Live-Minecraft-Token"]=str(cfg["token"])
 request=urllib.request.Request(str(cfg.get("url") or "http://127.0.0.1:8765/api/minecraft-studio/win"),data=body,headers=headers,method="POST")
 with urllib.request.urlopen(request,timeout=4) as response: return 200<=response.status<300

def sync_loop():
 while True:
  try:
   reply=rcon("lmsmountain status")
   if isinstance(reply,dict):
    ENGINE.update_world({"active":reply.get("active",False),"world":reply.get("world",""),"players":reply.get("players",[]),
     "start":reply.get("start",{}),"goal":reply.get("goal",{})})
    for event in reply.get("wins",[]):
     if event.get("eventId") not in {x.get("eventId") for x in STATUS["wins"]}:
      if send_win(event):
       STATUS["wins"]=(STATUS["wins"]+[event])[-30:]; rcon("lmsmountain ack "+str(event.get("eventId","")))
   STATUS.update({"rcon":"接続中","lastError":"","lastSync":time.time()})
  except Exception as exc: STATUS.update({"rcon":"未接続","lastError":str(exc)})
  time.sleep(2)

def run_effect(effect,sender,coins=0):
 result=ENGINE.receive(effect,sender,coins)
 for command in result["commands"]: rcon(command)
 return result
def enqueue_gacha(gid,sender,count=1):
 for _ in range(max(1,min(1000,int(count)))): GACHA_QUEUE.put((gid,sender))

def audio_fields(g,prefix):
 return {"soundUrl":g.get(prefix+"SoundUrl",""),"soundVolume":g.get(prefix+"SoundVolume",100),
         "soundSeconds":g.get(prefix+"SoundSeconds",0)}

def gacha_loop():
 while True:
  gid,sender=GACHA_QUEUE.get()
  try:
   g=STATE.get("gachas",{}).get(gid,{})
   if not g.get("enabled",True): continue
   max_spins=max(1,min(100,int(g.get("maxSpins",20)))) if g.get("continueEnabled") else 1
   for spin_no in range(1,max_spins+1):
    entries=[e for e in g.get("entries",[]) if float(e.get("weight",0))>0]
    if not entries: break
    spin=max(.3,min(60,float(g.get("spinSeconds",4))))
    event={"eventId":str(time.time_ns()),"gachaName":g.get("name","ガチャ"),"sender":sender,"state":"spinning",
      "result":"","at":time.time(),"spinSeconds":spin,"spinNumber":spin_no,"imageUrl":(g.get("customImageUrl","") if g.get("imageMode")=="custom" else "" if g.get("imageMode")=="none" else g.get("triggerGiftImageUrl","") or g.get("imageUrl","")),**audio_fields(g,"spin")}
    GACHA_EVENTS.append(event); time.sleep(spin)
    chosen=random.choices(entries,weights=[float(e.get("weight",1)) for e in entries],k=1)[0]
    effect=STATE.get("effects",{}).get(str(chosen.get("effectId","")))
    continued=bool(g.get("continueEnabled")) and spin_no<max_spins and random.random()<max(0,min(100,float(g.get("continueRate",50))))/100
    event.update({"state":"result","result":chosen.get("label") or (effect or {}).get("displayText") or (effect or {}).get("name","結果"),
                  "continued":continued,**audio_fields(g,"result")})
    if effect: run_effect(effect,sender)
    time.sleep(max(.3,min(30,float(g.get("resultSeconds",2)))))
    if not continued: break
    time.sleep(max(0,min(30,float(g.get("continueDelaySeconds",1)))))
  except Exception as exc: STATUS["lastError"]=str(exc)
  finally: GACHA_QUEUE.task_done()

def receive_social(body):
 kind=str(body.get("type") or body.get("eventType") or body.get("event") or "").lower()
 kind="follow" if "follow" in kind else "like" if "like" in kind else kind
 user_id=str(body.get("userId") or body.get("uniqueId") or (body.get("user") or {}).get("uniqueId") or "")
 sender=str(body.get("userName") or body.get("nickname") or (body.get("user") or {}).get("nickname") or user_id)
 runtime=STATE.setdefault("socialRuntime",deepcopy(DEFAULT["socialRuntime"])); targets=[]
 if kind=="follow":
  followed=set(runtime.get("followedUsers",[]))
  if not user_id or user_id in followed: return 0
  followed.add(user_id); runtime["followedUsers"]=list(followed)[-100000:]
  for typ,key in (("effect","effects"),("gacha","gachas")):
   targets += [(typ,k,v) for k,v in STATE[key].items() if v.get("enabled",True) and v.get("trigger")=="follow"]
 elif kind=="like":
  count=max(1,int(body.get("count",body.get("likeCount",1)))); likes=runtime.setdefault("individualLikes",{})
  before=int(likes.get(user_id,0)); after=before+count; likes[user_id]=after
  tb=int(runtime.get("totalLikes",0)); runtime["totalLikes"]=tb+count
  for typ,key in (("effect","effects"),("gacha","gachas")):
   for k,v in STATE[key].items():
    if not v.get("enabled",True) or v.get("trigger") not in ("like","total_like"): continue
    every=max(1,int(v.get("triggerAmount",100))); a,b=(before,after) if v["trigger"]=="like" else (tb,runtime["totalLikes"])
    targets += [(typ,k,v)]*min(50,b//every-a//every)
 else: raise ValueError("typeはfollowまたはlikeを指定してください")
 for typ,k,v in targets:
  if typ=="effect": run_effect(v,sender)
  else: enqueue_gacha(k,sender)
 save(); return len(targets)

def safe_asset(folder,name):
 name=Path(urllib.parse.unquote(name)).name
 target=(folder/name).resolve()
 return target if folder.resolve() in target.parents and target.is_file() else None

class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*_): pass
 def _json(self,body,status=200):
  data=json.dumps(body,ensure_ascii=False).encode(); self.send_response(status)
  self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store")
  self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
 def _body(self):
  length=min(int(self.headers.get("Content-Length","0")),30_000_000)
  return json.loads(self.rfile.read(length) or b"{}")
 def _file(self,target):
  data=target.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(target.name)[0] or "application/octet-stream")
  self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
 def do_GET(self):
  path=urllib.parse.urlparse(self.path).path
  if path in ("/api/state","/api/overlay"): return self._json(public_state())
  if path=="/api/gift-catalog":
   try:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/tiktok/gifts",timeout=3) as response: catalog=json.load(response)
    return self._json(catalog)
   except Exception as exc: return self._json({"gifts":[],"message":f"Live Overlay Studioから取得できません: {exc}"},503)
  if path.startswith("/user-sounds/"):
   target=safe_asset(SOUNDS_DIR,path.split("/",2)[-1]); return self._file(target) if target else self.send_error(404)
  if path.startswith("/user-images/"):
   target=safe_asset(IMAGES_DIR,path.split("/",2)[-1]); return self._file(target) if target else self.send_error(404)
  if path=="/": path="/index.html"
  target=(ROOT/path.lstrip("/")).resolve()
  if ROOT not in target.parents or not target.is_file(): return self.send_error(404)
  return self._file(target)
 def do_POST(self):
  path=urllib.parse.urlparse(self.path).path
  try:
   body=self._body()
   if path in ("/api/sound-upload","/api/image-upload"):
    is_sound=path.endswith("sound-upload"); folder=SOUNDS_DIR if is_sound else IMAGES_DIR
    raw=str(body.get("data","")); match=re.match(r"^data:([^;]+);base64,(.+)$",raw,re.S)
    if not match: raise ValueError("ファイル形式を確認してください")
    mime,payload=match.groups(); allowed=(mime.startswith("audio/") if is_sound else mime.startswith("image/"))
    if not allowed: raise ValueError("対応していないファイルです")
    data=base64.b64decode(payload,validate=True); limit=20_000_000 if is_sound else 8_000_000
    if len(data)>limit: raise ValueError("ファイルサイズが大きすぎます")
    ext=Path(str(body.get("name",""))).suffix.lower() or mimetypes.guess_extension(mime) or (".mp3" if is_sound else ".png")
    name=f"{time.time_ns()}{ext}"; (folder/name).write_bytes(data)
    return self._json({"ok":True,"url":("/user-sounds/" if is_sound else "/user-images/")+name})
   if path=="/api/config":
    with LOCK:
     for key in ("course","multiplier","overlay","rcon","winBridge","guns"):
      if isinstance(body.get(key),dict): STATE[key]=merge(STATE.get(key,{}),body[key])
     if isinstance(body.get("effects"),dict): STATE["effects"]=body["effects"]
     if isinstance(body.get("gachas"),dict): STATE["gachas"]=body["gachas"]
     global ENGINE
     old_world,old_events,old_mult=ENGINE.world_state,ENGINE.announcements,ENGINE.multiplier
     ENGINE=make_engine(); ENGINE.world_state=old_world; ENGINE.announcements=old_events
     ENGINE.multiplier.progress=old_mult.progress; ENGINE.multiplier.active_until=old_mult.active_until; save()
    return self._json({"ok":True,"state":public_state()})
   if path=="/api/course/apply":
    rcon(ENGINE.configure_command()); c=STATE["course"]
    rcon(f"lmsmountain environment {str(c.get('daylightFixed',True)).lower()} {str(c.get('clearWeather',True)).lower()}")
    return self._json({"ok":True,"message":"スタート・ゴール地点を適用しました"})
   if path in ("/api/effect/test","/api/test-effect"):
    effect=body.get("effect") or STATE["effects"].get(str(body.get("id")),{})
    return self._json({"ok":True,"result":run_effect(effect,body.get("sender","テスト"),int(body.get("coins",0))),"state":public_state()})
   if path=="/api/gift":
    event_type=str(body.get("eventType") or body.get("type") or "").lower()
    if "follow" in event_type or "like" in event_type: return self._json({"ok":True,"triggered":receive_social(body)})
    gift=str(body.get("giftName") or body.get("giftId") or ""); sender_id=str(body.get("userId") or body.get("uniqueId") or "")
    sender=str(body.get("userName") or body.get("nickname") or sender_id); repeat=max(1,int(body.get("repeatCount",1))); fired=0
    for effect in STATE["effects"].values():
     if not effect.get("enabled",True) or effect.get("gachaOnly") or effect.get("trigger","gift")!="gift" or gift not in {str(effect.get("gift","")),str(effect.get("giftId","")),str(effect.get("giftName",""))}: continue
     allowed=str(effect.get("userId","")).strip()
     if allowed and allowed!=sender_id: continue
     for _ in range(repeat): run_effect(effect,sender,int(body.get("coins",0))); fired+=1
    for gid,g in STATE.get("gachas",{}).items():
     if not g.get("enabled",True) or g.get("trigger","gift")!="gift" or gift not in {str(g.get("gift","")),str(g.get("triggerGiftId","")),str(g.get("triggerGiftName",""))}: continue
     allowed=str(g.get("userId","")).strip()
     if allowed and allowed!=sender_id: continue
     enqueue_gacha(gid,sender,repeat); fired+=repeat
    return self._json({"ok":True,"fired":fired})
   if path=="/api/social": return self._json({"ok":True,"triggered":receive_social(body)})
   if path in ("/api/gacha/test","/api/test-gacha"):
    enqueue_gacha(str(body.get("id")),body.get("sender","テスト"),int(body.get("count",1)))
    return self._json({"ok":True,"queued":GACHA_QUEUE.qsize()})
   if path=="/api/server/prepare":
    result=LOCAL.prepare(bool(body.get("eulaAccepted"))); STATE["rcon"].update({"host":"127.0.0.1","port":25576,"password":result["password"]}); save()
    return self._json({"ok":True,"status":LOCAL.status(),"state":public_state()})
   if path=="/api/server/start": return self._json({"ok":True,"status":LOCAL.start()})
   if path=="/api/server/stop": return self._json({"ok":True,"status":LOCAL.stop(STATE["rcon"])})
   if path=="/api/reset": rcon("lmsmountain reset"); return self._json({"ok":True})
   return self._json({"ok":False,"message":"不明な操作です"},404)
  except Exception as exc: return self._json({"ok":False,"message":str(exc)},400)

def make_server():
 Thread(target=sync_loop,daemon=True).start(); Thread(target=gacha_loop,daemon=True).start()
 return ThreadingHTTPServer((HOST,PORT),Handler)
if __name__=="__main__":
 print(f"Live Minecraft Mountain Studio v{APP_VERSION}: http://{HOST}:{PORT}/"); make_server().serve_forever()
