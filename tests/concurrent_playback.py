"""Exercise real HTTP handlers against disposable settings and spin plans."""
import concurrent.futures
import copy
import importlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def exercise(module_name):
    app = importlib.import_module(module_name)
    with tempfile.TemporaryDirectory(prefix="overlay-load-") as directory:
        app.ROOT = Path(directory)
        app.STATE = app.ROOT / "state.json"
        state, _ = app.normalize_state(copy.deepcopy(app.DEFAULT))
        state["loadTestPadding"] = "x" * 500_000
        for index in range(2):
            event = {
                **copy.deepcopy(app.SLOT_EMPTY_EVENT),
                "id": 100 + index, "active": True, "createdAt": time.time(),
                "patternId": state["slotMachine"]["patterns"][0]["id"],
                "patternName": "load-test", "sign": "plus", "initialSpins": 2000,
                "isTest": False,
                "spins": [{"kind": "miss", "win": 0, "addedSpins": 0,
                           "reels": ["7"] * 3, "reelImages": [""] * 3}
                          for _ in range(2000)],
            }
            if index == 0:
                state["slotMachine"]["event"] = event
            else:
                state["slotMachine"]["queue"] = [event]
        state["gacha"]["event"] = {
            "id": 500, "type": "gacha", "active": True, "isTest": False,
            "winSign": "plus", "choice": "", "createdAt": time.time(),
            "rounds": [{"delta": 1, "total": i + 1} for i in range(20)],
            "appliedRounds": [], "total": 20,
        }
        app._externalize_slot_spin_plans(state, cleanup=False)
        app.STATE.write_text(json.dumps(state), encoding="utf-8")
        initial_size = app.STATE.stat().st_size
        plans = {p.name: p.read_bytes() for p in app.ROOT.glob("slot_plan_*.json")}
        normalization_calls = 0
        original_normalize = app.normalize_state
        def counted(value):
            nonlocal normalization_calls
            normalization_calls += 1
            return original_normalize(value)
        app.normalize_state = counted
        http = app.LocalThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(http.server_port)
        def request(path, body=None):
            started = time.perf_counter()
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(base + path, data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as response:
                result = json.load(response)
            return result, time.perf_counter() - started
        timings = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=11) as pool:
                for index in range(20):
                    paths = ["/api/overlay/win", "/api/overlay/gift-history",
                             "/api/overlay/slot", "/api/overlay/slot",
                             "/api/overlay/machine-stats?id=slot-pattern-1",
                             "/api/overlay/machine-stats?id=slot-pattern-1",
                             "/api/overlay/gacha", "/api/overlay/basic"]
                    jobs = [pool.submit(request, path) for path in paths]
                    jobs += [pool.submit(request, "/api/slot/apply-spin",
                                         {"eventId": event_id, "spinIndex": index})
                             for event_id in (100, 101)]
                    jobs.append(pool.submit(request, "/api/gacha/apply-round",
                                            {"eventId": 500, "roundIndex": index}))
                    for job in jobs:
                        result, elapsed = job.result()
                        assert result.get("ok", True), result
                        timings.append(elapsed)
            final = json.loads(app.STATE.read_text(encoding="utf-8"))
            assert final["winCounter"]["currentWin"] == 20
            assert final["slotMachine"]["event"]["appliedSpins"] == 20
            assert final["slotMachine"]["queue"][0]["appliedSpins"] == 20
            assert len(final["gacha"]["event"]["appliedRounds"]) == 20
            # Retrying an acknowledgement must not add WIN twice.
            assert request("/api/gacha/apply-round", {"eventId": 500, "roundIndex": 19})[0]["ok"]
            assert json.loads(app.STATE.read_text())["winCounter"]["currentWin"] == 20
            if module_name == "server":
                assert normalization_calls == 0, normalization_calls
                assert not final["slotMachine"]["event"]["spins"]
                assert not final["slotMachine"]["queue"][0]["spins"]
                assert app.STATE.stat().st_size < initial_size * 1.05
                assert plans == {p.name: p.read_bytes() for p in app.ROOT.glob("slot_plan_*.json")}
                assert request("/api/gacha/complete", {"eventId": 500})[0]["ok"]
                completed = json.loads(app.STATE.read_text())
                assert completed["gacha"]["history"][0]["result"] == 20
                assert completed["slotMachine"]["queue"][0]["appliedSpins"] == 20
                # Both-sign production results apply exactly once.
                completed["gacha"]["event"] = {
                    "id": 501, "type": "gacha", "active": True,
                    "winSign": "both", "total": 7, "choice": "", "isTest": False,
                }
                app.STATE.write_text(json.dumps(completed))
                assert request("/api/gacha/choice-ready", {"eventId": 501})[0]["ok"]
                assert request("/api/gacha/choose-sign", {"eventId": 501, "choice": "minus"})[0]["ok"]
                assert not request("/api/gacha/choose-sign", {"eventId": 501, "choice": "minus"})[0]["ok"]
                assert json.loads(app.STATE.read_text())["winCounter"]["currentWin"] == 13
                # A test result must not change the real WIN counter.
                test_state = json.loads(app.STATE.read_text())
                test_state["gacha"]["event"] = {
                    "id": 502, "type": "gacha", "active": True,
                    "winSign": "plus", "isTest": True,
                    "rounds": [{"delta": 100}], "appliedRounds": [],
                }
                app.STATE.write_text(json.dumps(test_state))
                assert request("/api/gacha/apply-round", {"eventId": 502, "roundIndex": 0})[0]["ok"]
                assert json.loads(app.STATE.read_text())["winCounter"]["currentWin"] == 13
                assert normalization_calls == 0
            ordered = sorted(timings)
            print(module_name, json.dumps({
                "requests": len(timings), "median_ms": round(statistics.median(timings)*1000, 1),
                "p95_ms": round(ordered[int(len(ordered)*.95)]*1000, 1),
                "max_ms": round(max(timings)*1000, 1), "normalizations": normalization_calls,
                "initial_bytes": initial_size, "final_bytes": app.STATE.stat().st_size,
                "slot1_spins": final["slotMachine"]["event"]["appliedSpins"],
                "slot2_spins": final["slotMachine"]["queue"][0]["appliedSpins"],
                "win": final["winCounter"]["currentWin"],
            }))
        finally:
            http.shutdown()
            http.server_close()

if __name__ == "__main__":
    exercise("server")
