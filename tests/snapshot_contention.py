"""Reproduce three-second writer contention against real HTTP endpoints."""
import concurrent.futures
import copy
import importlib
import json
import sys
from pathlib import Path
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def run(module_name, improved):
    app=importlib.import_module(module_name)
    with tempfile.TemporaryDirectory(prefix="overlay-contention-") as directory:
        app.ROOT=Path(directory)
        app.STATE=app.ROOT/"state.json"
        state,_=app.normalize_state(copy.deepcopy(app.DEFAULT))
        state["loadTestPadding"]="x"*500000
        state["winCounter"]["currentWin"]=41
        app.STATE.write_text(json.dumps(state),encoding="utf-8")
        app.read_cached_overlay_source()
        http=app.LocalThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        base=f"http://127.0.0.1:{http.server_port}"
        def get(path):
            started=time.perf_counter()
            with urllib.request.urlopen(base+path,timeout=10) as response:
                payload=json.load(response)
            return payload,time.perf_counter()-started
        holding=threading.Event()
        def slow_write():
            with app.STATE_LOCK:
                data=json.loads(app.STATE.read_text())
                data["winCounter"]["currentWin"]=42
                # Emulate a slow disk write while STATE_LOCK is held.
                app.STATE.write_text(json.dumps(data),encoding="utf-8")
                holding.set()
                time.sleep(3)
                if improved:
                    app.write_state_file(data)
        writer=threading.Thread(target=slow_write)
        writer.start()
        assert holding.wait(2)
        try:
            health,health_seconds=get("/api/health")
            assert health_seconds<.5
            paths=["/api/overlay/win","/api/overlay/slot","/api/overlay/slot",
                   "/api/overlay/basic","/api/overlay/gift-history","/api/overlay/gacha",
                   "/api/slot/status","/api/tiktok/gifts"]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                replies=list(pool.map(get,paths))
            maximum=max(duration for _,duration in replies)
            if improved:
                assert maximum<.5, maximum
                assert replies[0][0]["winCounter"]["currentWin"]==41
            else:
                assert maximum>2, maximum
            writer.join()
            latest,_=get("/api/overlay/win")
            assert latest["winCounter"]["currentWin"]==42
            if improved:
                diagnostics,_=get("/api/diagnostics")
                assert diagnostics["metrics"]["stateLockHeld"]["maxMs"]>=2900
                assert diagnostics["metrics"]["snapshotServedWhileBusy"]["count"]>=1
                # Malformed external writes must not replace the last good
                # snapshot with empty defaults or alter the damaged file.
                app.STATE.write_text("{broken",encoding="utf-8")
                retained,_=get("/api/overlay/win")
                assert retained["winCounter"]["currentWin"]==42
                assert app.STATE.read_text()=="{broken"
            print(module_name,json.dumps({"health_ms":round(health_seconds*1000,1),
                  "slowest_overlay_ms":round(maximum*1000,1),
                  "writer_pause_ms":3000,"committed_win":42}))
        finally:
            writer.join()
            http.shutdown()
            http.server_close()

if __name__ == "__main__":
    run("server",True)
