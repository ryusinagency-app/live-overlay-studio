import copy
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as app
from preset_board import normalize_presets

with tempfile.TemporaryDirectory() as directory:
    app.ROOT=Path(directory);app.STATE=app.ROOT/'state.json'
    state=copy.deepcopy(app.DEFAULT)
    state['presets']={'boards':[{'id':'b','name':'案内','style':'neon','transparent':True,'fontFamily':'meiryo','customCss':'.presetCard {border-width:2px}',
                               'items':[{'id':'i','giftName':'バラ','giftId':'5655','giftImageUrl':'https://example.com/rose.png','description':'テスト <img onerror=alert(1)>','imageUrl':'/saved.png'}]}]}
    app.write_state(state)
    before=app.read_state()['presets'];assert before['boards'][0]['items'][0]['description'].startswith('テスト')
    assert normalize_presets({'boards':[{'items':[{'imageUrl':'javascript:alert(1)'}]}]})['boards'][0]['items'][0]['imageUrl']==''
    assert normalize_presets({'boards':9})=={'boards':[]}
    http=app.LocalThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{http.server_port}'
    def get(etag=None):
        request=urllib.request.Request(origin+'/api/overlay/presets?id=b',headers={'If-None-Match':etag} if etag else {})
        try:
            with urllib.request.urlopen(request,timeout=3) as r:return r.status,r.headers, r.read()
        except urllib.error.HTTPError as r:
            if r.code==304:return r.code,r.headers,b''
            raise
    try:
        status,headers,body=get();assert status==200 and len(body)<3000
        etag=headers['ETag'];assert get(etag)[0]==304
        assert set(json.loads(body))=={'board'}
        # Slot/WIN commits do not invalidate a static board or send its images again.
        state=app.read_state();state['winCounter']['currentWin']=14
        with app.STATE_LOCK:app.write_state_file(state)
        assert get(etag)[0]==304
        original_normalize=app.normalize_state
        app.normalize_state=lambda *_:(_ for _ in ()).throw(AssertionError('no full-state normalization on display polls'))
        # A blocked writer cannot block this overlay's snapshot read.
        with app.STATE_LOCK:
            start=time.perf_counter();assert get(etag)[0]==304;elapsed=time.perf_counter()-start
        assert elapsed<.5
        app.normalize_state=original_normalize
        request=urllib.request.Request(origin+'/api/presets/media',data=json.dumps({'boardId':'b','itemId':'i','name':'test.png','dataUrl':'data:image/png;base64,YWJj'}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as r:uploaded=json.load(r)
        assert uploaded['ok'] and uploaded['item']['imageUrl'].startswith('/preset_')
        fresh=app.read_state();assert fresh['winCounter']['currentWin']==14
        assert fresh['presets']['boards'][0]['items'][0]['giftImageUrl']=='https://example.com/rose.png'
        assert get(etag)[0]==200
        saved=fresh['presets'];app.write_state(fresh);assert app.read_state()['presets']==saved
        print(f'PASS preset persistence, isolated small API/ETag, unchanged WIN commits, nonblocking snapshot ({elapsed*1000:.1f}ms), image upload, safe image URLs')
    finally:http.shutdown();http.server_close()
