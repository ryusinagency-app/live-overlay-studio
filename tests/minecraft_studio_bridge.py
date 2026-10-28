import copy
import json
import tempfile
import threading
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


normalized, _ = server.normalize_state({
    'minecraftStudioBridge': {
        'enabled': True,
        'url': 'http://127.0.0.1:8775/api/gift',
        'token': 'test-token',
    }
})
assert normalized['minecraftStudioBridge']['enabled'] is True
assert normalized['minecraftStudioBridge']['token'] == 'test-token'

with tempfile.TemporaryDirectory() as directory:
    original_state = server.STATE
    server.STATE = Path(directory) / 'state.json'
    data = copy.deepcopy(server.DEFAULT)
    data['winCounter']['currentWin'] = 7
    data['minecraftStudioBridge']['token'] = 'test-token'
    server.write_state_file(data)
    httpd = server.LocalThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{httpd.server_port}/api/minecraft-studio/win'

        def post():
            request = urllib.request.Request(
                url,
                data=json.dumps({'eventId': 'win-1', 'amount': 3}).encode(),
                headers={'Content-Type': 'application/json', 'X-Live-Minecraft-Token': 'test-token'},
                method='POST',
            )
            return json.load(urllib.request.urlopen(request, timeout=2))

        first = post()
        duplicate = post()
        saved = json.loads(server.STATE.read_text())
        assert first['currentWin'] == 10
        assert duplicate['duplicate'] is True
        assert saved['winCounter']['currentWin'] == 10
    finally:
        httpd.shutdown()
        httpd.server_close()
        server.STATE = original_state

print('PASS Live Minecraft Studio bridge config and exactly-once WIN endpoint')
