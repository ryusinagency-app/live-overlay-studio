"""Ranking persistence and real HTTP handlers against disposable state only."""
import ast, copy, json, tempfile, threading, time, urllib.request
from pathlib import Path

root=Path(__file__).resolve().parents[1]
tree=ast.parse((root/'server.py').read_text())
nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef)) or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEFAULT' for t in n.targets)]
ns={'__name__':'ranking_rules'}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'server.py','exec'),ns)
with tempfile.TemporaryDirectory(prefix='ranking-rules-') as folder:
 ns.update(ROOT=root,STATE=Path(folder)/'state.json',STATE_LOCK=threading.Lock(),SERVER_STARTED_AT=0,JST=ns['timezone'](ns['timedelta'](hours=9)),OVERLAY_SNAPSHOT_LOCK=threading.Lock(),OVERLAY_SNAPSHOT_CACHE={'signature':None,'at':0,'state':None},TIKTOK_GIFT_CATALOG_LOCK=threading.Lock(),TIKTOK_GIFT_CATALOG=[])
 def write(data): ns['write_state'](data)
 def read(): return ns['read_state']()
 def draw(scope,win,sets,name='A',test=False):
  data=read();g=data[scope];g['event']={'id':7,'type':'gacha' if scope=='gacha' else 'pachinko-gacha','active':True,'senderName':name,'avatarUrl':'https://example.com/avatar.png','patternName':str(sets)+'セットのガチャ','createdAt':time.time(),'isTest':test,'winSign':'minus','total':-win if scope=='gacha' else win,'hitSpin':1,'rounds':[{'continued':i<sets-1} for i in range(sets)]};write(data)
  assert ns['complete_gacha_event' if scope=='gacha' else 'complete_pachinko_event'](7)
  assert not ns['complete_gacha_event' if scope=='gacha' else 'complete_pachinko_event'](7)
 write(copy.deepcopy(ns['DEFAULT']))
 for scope in ('gacha','pachinkoGacha'):
  draw(scope,100,12);draw(scope,900,3);draw(scope,1,1,test=True)
  data=read();g=data[scope];record=g['bestRecords'][0]
  assert record['bestWin']==900 and record['winRecord']['setCount']==3 and record['winRecord']['patternName']=='3セットのガチャ'
  assert record['bestSet']==12 and record['setRecord']['result']==-100
  assert record['winRecord']['avatarUrl']=='https://example.com/avatar.png'
  assert len(g['history'])==2 and g['history'][0]['setCount']==3
  # Evict all old history while preserving the independent personal bests.
  g['history']=[{'id':i,'senderName':'B','result':1,'total':1,'setCount':1,'createdAt':i} for i in range(200)];write(data)
  record=read()[scope]['bestRecords'][0];assert record['bestWin']==900 and record['bestSet']==12
 data=read();data['gacha']['rankingViews']['set'].update(limit=100,avatarSize=160,nameScroll=False,textScrollSpeed=150,nameTemplate='配信者 {name}',scoreTemplate='{set}SET / {win}WIN',titleBg='#123456',titleOpacity=47);write(data)
 snapshot=ns['read_overlay_state']('rankings');assert set(snapshot['boards'])=={'winSet','winBest','pachinkoBest'}
 assert len(ns['read_overlay_state']('gacha-history')['boards']['winHistory']['rows'])==200
 assert snapshot['boards']['winSet']['rows'][0]['setCount']==12
 assert snapshot['boards']['winSet']['rows'][0]['result']==-100
 assert snapshot['boards']['winBest']['rows'][0]['setCount']==3
 assert snapshot['boards']['pachinkoBest']['rows'][0]['result']==-900
 assert snapshot['boards']['winSet']['view']['nameScroll'] is False
 assert snapshot['boards']['winSet']['view']['titleBg']=='#123456'
 assert snapshot['boards']['winSet']['view']['titleOpacity']==47
 assert 'bestRecords' not in ns['read_overlay_state']('gacha')['gacha'] and 'rankingViews' not in ns['read_overlay_state']('gacha')['gacha']
 print('PASS rankings: independent metrics retain actual record details, signed wins, first SET, test isolation and survival past 200 histories')
 # Legacy history migration and unsafe image filtering.
 legacy=copy.deepcopy(ns['DEFAULT']);legacy['gacha']['history']=[{'id':1,'senderName':'legacy','continueCount':0,'result':-500,'avatarUrl':'javascript:bad'}];write(legacy)
 row=read()['gacha']['bestRecords'][0];assert row['bestSet']==1 and row['bestWin']==500 and row['winRecord']['avatarUrl']==''
 before=read();write(before);assert read()==before
 # A first-render race in older builds could save untouched ranking inputs as
 # blank templates with black colors.  Recover those records automatically.
 broken=read();broken['gacha']['rankingViews']['set'].update(nameTemplate='',patternTemplate='',scoreTemplate='',textColor='#000000',cardBg='#000000',cardBorder='#000000');write(broken)
 repaired=read()['gacha']['rankingViews']['set'];assert repaired['nameTemplate']=='{name}' and repaired['patternTemplate']=='{gacha}' and repaired['scoreTemplate']=='{set}SET {win}WIN'
 assert repaired['textColor']=='#ffffff' and repaired['cardBg']=='#17181e' and repaired['cardBorder']=='#ffcf59'
 # Actual gift dispatch carries the icon into both pending events.
 data=read();data['gacha']['patterns'][0]['giftName']='rose';data['pachinkoGacha']['patterns']=[{'id':'p','name':'P','giftName':'rose'}];write(data)
 assert ns['process_gift_event']('rose',sender_name='gift viewer',avatar_url='https://example.com/gift-avatar.png',gift_info={'name':'rose','price':1,'imageUrl':'https://example.com/rose.png'})
 data=read();assert data['gacha']['event']['avatarUrl']==data['pachinkoGacha']['event']['avatarUrl']=='https://example.com/gift-avatar.png'
 print('PASS migration: existing history, stable reload and real gift avatar propagation')
 server=ns['ThreadingHTTPServer'](('127.0.0.1',0),ns['Handler']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  base='http://127.0.0.1:'+str(server.server_port)
  def get(path): return urllib.request.urlopen(base+path)
  with get('/api/overlay/rankings') as response:
   assert 'no-store' in response.headers['Cache-Control'];assert 'boards' in json.load(response)
  with get('/api/overlay/gacha-history') as response: assert 'winHistory' in json.load(response)['boards']
  for asset in ('overlay_win_gacha_best_set.html','overlay_win_gacha_best_win.html','overlay_pachinko_best_win.html','overlay_best_ranking.js','overlay_best_ranking.css','ranking_controls.js'):
   assert asset in (root/'build_windows_app.bat').read_text() and asset in (root/'server.py').read_text()
   with get('/'+asset) as response: assert response.status==200
  # A stale control save must not erase personal records or recent results.
  stale=read();draw('gacha',777,7,'new');draw('pachinkoGacha',888,8,'newP');stale['gacha']['history']=[];stale['gacha']['bestRecords']=[];stale['pachinkoGacha']['bestRecords']=[]
  req=urllib.request.Request(base+'/api/state',data=json.dumps(stale).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as response: assert response.status==200
  assert any(row['senderName']=='new' and row['bestWin']==777 for row in read()['gacha']['bestRecords'])
  assert any(row['senderName']=='new' for row in read()['gacha']['history'])
  assert any(row['senderName']=='newP' and row['bestWin']==888 for row in read()['pachinkoGacha']['bestRecords'])
 finally: server.shutdown();server.server_close();thread.join()
 print('PASS HTTP: compact ranking snapshots, all packaged assets and stale-save preservation')
