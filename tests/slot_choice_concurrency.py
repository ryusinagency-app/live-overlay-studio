"""Per-machine choice acknowledgements while the other slot keeps spinning."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app

def event(event_id,pattern,ready,total=0,is_test=False):
    return {**copy.deepcopy(app.SLOT_EMPTY_EVENT), "id":event_id,"type":"slot",
            "active":True,"createdAt":time.time(),"patternId":pattern,
            "patternName":pattern,"senderName":"sender-"+str(event_id),
            "sign":"both","choiceReady":ready,"total":total,"isTest":is_test,
            "spins":[{"kind":"hit","win":total,"addedSpins":0}]*3,
            "appliedSpins":3 if ready else 1}

with tempfile.TemporaryDirectory(prefix="slot-choices-") as directory:
    app.ROOT=Path(directory);app.STATE=app.ROOT/"state.json"
    state,_=app.normalize_state(copy.deepcopy(app.DEFAULT))
    base=copy.deepcopy(state)
    def write(primary,queued):
        state=copy.deepcopy(base)
        state["slotMachine"]["event"]=primary
        state["slotMachine"]["queue"]=queued
        with app.STATE_LOCK:
            app.write_state_file(state)
    http=app.LocalThreadingHTTPServer(("127.0.0.1",0),app.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    def request(path,body=None):
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(f"http://127.0.0.1:{http.server_port}"+path,data=data,
                                   headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=5) as response:
            return json.load(response)
    def choose(event_id,sign):
        return request("/api/slot/choose-sign",{"eventId":event_id,"choice":sign})
    try:
        # Primary slot in AT; queued dedicated slot waiting for its own sign.
        write(event(101,"slot-1",False),[event(102,"slot-2",True,100)])
        status=request("/api/slot/status")["slotMachine"]
        assert [item["id"] for item in status["choiceEvents"]]==[102]
        assert choose(102,"minus")["ok"]
        saved=json.loads(app.STATE.read_text())
        assert saved["winCounter"]["currentWin"]==-100
        assert saved["slotMachine"]["event"]["id"]==101
        assert saved["slotMachine"]["event"]["appliedSpins"]==1
        assert not saved["slotMachine"]["queue"]
        assert not choose(102,"minus")["ok"]  # no duplicate application
        assert request("/api/slot/apply-spin",{"eventId":101,"spinIndex":1})["ok"]

        # Shared shortcut resolves the actual waiter rather than the AT player.
        write(event(201,"slot-1",False),[event(202,"slot-2",True,70)])
        original=app.normalize_state
        app.normalize_state=lambda *_: (_ for _ in ()).throw(AssertionError("choice normalized all settings"))
        app.dispatch_hotkey_action({"type":"slotChoice","choice":"plus"})
        app.normalize_state=original
        saved=json.loads(app.STATE.read_text())
        assert saved["winCounter"]["currentWin"]==70
        assert saved["slotMachine"]["event"]["id"]==201

        # Primary choosing while the other player is mid-spin: no new start
        # delay may hide/restart the existing dedicated overlay.
        write(event(301,"slot-1",True,50),[event(302,"slot-2",False)])
        assert choose(301,"plus")["ok"]
        saved=json.loads(app.STATE.read_text())
        assert saved["slotMachine"]["event"]["id"]==302
        assert saved["slotMachine"]["event"]["appliedSpins"]==1
        assert not saved["slotMachine"]["event"].get("startAfter")
        assert request("/api/slot/apply-spin",{"eventId":302,"spinIndex":1})["ok"]

        # Both players choosing: target either independently.
        write(event(401,"slot-1",True,30),[event(402,"slot-2",True,80)])
        assert len(request("/api/slot/status")["slotMachine"]["choiceEvents"])==2
        assert choose(402,"minus")["ok"]
        assert [item["id"] for item in request("/api/slot/status")["slotMachine"]["choiceEvents"]]==[401]
        assert choose(401,"plus")["ok"]
        saved=json.loads(app.STATE.read_text())
        assert saved["winCounter"]["currentWin"]==-50
        assert not saved["slotMachine"]["event"]["active"]
        assert len(saved["slotMachine"]["history"])==2

        # Test results stay isolated from real WIN.
        write(event(501,"slot-1",False),[event(502,"slot-2",True,100,True)])
        assert choose(502,"plus")["ok"]
        assert json.loads(app.STATE.read_text())["winCounter"]["currentWin"]==0
        print("PASS: independent choices; other AT progresses; shared shortcut; no restart on promotion; no duplicate WIN; tests isolated")
    finally:
        http.shutdown();http.server_close()
