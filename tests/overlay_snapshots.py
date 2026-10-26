"""Exercise actual handlers against temporary settings, without starting the app."""
import ast
import copy
import json
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
control_source = (root / 'control.html').read_text(encoding='utf-8')
assert "querySelectorAll('.overlayUrl[data-view]')" in control_source
assert "const path=paths[input.dataset.view];if(!path)return" in control_source
tree = ast.parse((root / 'server.py').read_text(encoding='utf-8'))
nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))
         or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'DEFAULT' for target in node.targets))]
ns = {'__name__': 'overlay_snapshot_tests'}
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'server.py', 'exec'), ns)
gift = ns['normalize_gift_catalog']([{'id': 1, 'name': '画像付きギフト',
                                      'image_url': 'https://example.com/gift.webp'}])[0]
assert gift['imageUrl'] == 'https://example.com/gift.webp'

with tempfile.TemporaryDirectory(prefix='overlay-snapshots-') as folder:
    clock = [100]
    ns.update(ROOT=Path(folder), STATE=Path(folder) / 'state.json', STATE_LOCK=threading.Lock(),
              OVERLAY_SNAPSHOT_LOCK=threading.Lock(), OVERLAY_SNAPSHOT_CACHE={'signature': None, 'at': 0, 'state': None},
              SERVER_STARTED_AT=0, JST=ns['timezone'](ns['timedelta'](hours=9)),
              time=SimpleNamespace(time=time.time, monotonic=lambda: clock[0]))
    data = copy.deepcopy(ns['DEFAULT'])
    data['gacha']['patterns'] = [{'id': 'p' + str(i), 'name': 'pattern ' + str(i), 'outcomeMode': 'weighted',
                                 'outcomes': [{'value': n, 'probability': 1, 'resultImageUrl': f'/number-{n}.png'} for n in range(100)]}
                                for i in range(12)]
    data['gacha']['event'].update(id=7, type='gacha', active=True, patternId='p3', createdAt=time.time(),
                                  winSign='both', choice='', rounds=[{'delta': 50, 'total': 50, 'phase': 'upper'}])
    data['gacha']['history'] = [{'id': i, 'senderName': 'viewer ' + str(i), 'result': i, 'createdAt': time.time()} for i in range(200)]
    data['winCounter'].update(currentWin=21, addSoundUrl='/add.mp3')
    ns['write_state'](data)
    calls = [0]
    actual_read = ns['read_state']
    def counted_read():
        calls[0] += 1
        return actual_read()
    ns['read_state'] = counted_read
    # Warm normalization if it needs a one-time migration.
    ns['read_overlay_state']('win')
    ns['read_overlay_state']('win')
    before = calls[0]
    win = ns['read_overlay_state']('win')
    gacha = ns['read_overlay_state']('gacha')
    assert calls[0] == before, 'two renderers share a current disk snapshot'
    assert win['winCounter']['currentWin'] == 21 and win['winCounter']['addSoundUrl'] == '/add.mp3'
    assert 'winProfiles' not in win and 'gacha' not in win and 'giftWall' not in win
    assert len(gacha['gacha']['patterns']) == 1 and gacha['gacha']['patterns'][0]['id'] == 'p3'
    assert gacha['gacha']['event']['rounds'][0]['delta'] == 50
    assert 'queue' not in gacha['gacha'] and 'history' not in gacha['gacha']
    gacha['gacha']['patterns'][0]['name'] = 'mutated copy'
    assert ns['read_overlay_state']('gacha')['gacha']['patterns'][0]['name'] != 'mutated copy'
    updated = actual_read()
    updated['winCounter']['currentWin'] = 22
    updated['gacha']['event'].update(choiceReady=True, choice='minus')
    ns['write_state'](updated)
    assert ns['read_overlay_state']('win')['winCounter']['currentWin'] == 22, 'writes invalidate immediately'
    assert ns['read_overlay_state']('gacha')['gacha']['event']['choice'] == 'minus'
    before = calls[0]
    clock[0] += .21
    ns['read_overlay_state']('win')
    assert calls[0] > before, 'time-dependent settings are periodically refreshed'
    full_size = len(json.dumps(actual_read()).encode())
    win_size = len(json.dumps(win).encode())
    gacha_size = len(json.dumps(gacha).encode())
    assert win_size < full_size / 10 and gacha_size < full_size / 2
    print(f'PASS snapshot content/cache/invalidation: full={full_size}, WIN={win_size}, gacha={gacha_size} bytes (synthetic 12-pattern fixture)')

    server = ns['LocalThreadingHTTPServer'](('127.0.0.1', 0), ns['Handler'])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for kind in ('win', 'gacha'):
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/overlay/{kind}', timeout=5) as response:
                payload = json.load(response)
                assert response.status == 200 and 'no-store' in response.headers['Cache-Control']
                assert ('winCounter' if kind == 'win' else 'gacha') in payload
        print('PASS live HTTP routes and no-store headers')
    finally:
        server.shutdown()
        server.server_close()
