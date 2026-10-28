"""Round-trip settings and actual media upload handlers without user data."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1] if Path(__file__).parent.name=='tests' else Path(__file__).parent))
import server as app

with tempfile.TemporaryDirectory(prefix='pachinko-media-') as directory:
    app.ROOT=Path(directory);app.STATE=app.ROOT/'state.json'
    state=copy.deepcopy(app.DEFAULT)
    state['pachinkoGacha']['patterns']=[{'id':'p','name':'existing','hitAudioUrl':'/legacy.mp3','stopAudioUrl':'/stop.mp3'}]
    state['winCounter']['currentWin']=-101
    normalized,_=app.normalize_state(state)
    p=normalized['pachinkoGacha']['patterns'][0]
    assert p['hitAudioLoop'] is True and p['stopAudioLoop'] is False
    assert p['preAlert1AudioLoop'] is False and p['spinBeepLoop'] is True
    for stage in app.pachinko_phase_media_stages():
        p[stage+'AudioLoop']=True;p[stage+'VideoLoop']=False
        p[stage+'AudioVolume']=39;p[stage+'AnimationUrl']='/'+stage+'.png'
    p['spinBeepLoop']=False;p['preAlert1AudioLoop']=True
    app.write_state(normalized)
    saved=app.read_state()['pachinkoGacha']['patterns'][0]
    for stage in app.pachinko_phase_media_stages():
        assert saved[stage+'AudioLoop'] is True and saved[stage+'VideoLoop'] is False
        assert saved[stage+'AudioVolume']==39 and saved[stage+'AnimationUrl']=='/'+stage+'.png'
    assert saved['spinBeepLoop'] is False and saved['preAlert1AudioLoop'] is True
    http=app.LocalThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    def post(body):
        request=urllib.request.Request(f'http://127.0.0.1:{http.server_port}/api/pachinko/media',data=json.dumps({'patternId':'p',**body}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=5) as response:return json.load(response)
    try:
        for stage in app.pachinko_phase_media_stages():
            for kind,mime in [('audio','audio/mpeg'),('animation','image/png')]:
                response=post({'stage':stage,'kind':kind,'name':'sample','dataUrl':f'data:{mime};base64,YWJj'})
                saved=response['pachinkoGacha']['patterns'][0]
                assert saved[stage+('AudioUrl' if kind=='audio' else 'AnimationUrl')].startswith('/pachinko_'+stage+'_')
                assert saved[stage+'AudioLoop'] is True
        post({'stage':'atHit','kind':'audio','clear':True})
        final=app.read_state()
        assert final['pachinkoGacha']['patterns'][0]['atHitAudioUrl']==''
        assert final['pachinkoGacha']['patterns'][0]['hitAudioUrl']=='/legacy.mp3'
        assert final['winCounter']['currentWin']==-101
    finally:http.shutdown();http.server_close()
print('PASS: legacy defaults, all phase setting round-trips, audio/image upload and clear, existing WIN/settings retained')
