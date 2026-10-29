"""Run explicitly against an isolated Paper test server, never the user's world."""
import json
import os
import time
from rcon import RconClient


def run():
    with RconClient("127.0.0.1", int(os.environ.get("LMS_TEST_RCON_PORT", "25595")), "lms-isolated-test") as c:
        def state(): return json.loads(c.command("lmsarena status"))
        def wait_for(predicate, seconds=5):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                s = state()
                if predicate(s): return s
                time.sleep(.1)
            raise AssertionError(state())
        def generate(width, floor=True, clear=True):
            reply = json.loads(c.command(f"lmsarena generate world 0 80 0 {width} {width} 3 minecraft:glass minecraft:diamond_block 2 1 {str(clear).lower()} {str(floor).lower()} 20 10 3"))
            assert reply["ok"], reply
            wait_for(lambda s: s["ready"])
        def matches(x, y, z, block):
            reply = c.command(f"execute if block {x} {y} {z} {block}")
            return "Test passed" in reply

        generate(3)
        assert matches(1, 79, 1, "glass"), "missing floor"
        assert matches(-1, 81, 1, "glass"), "missing wall"
        assert matches(1, 83, 1, "air"), "roof must be open"
        # Vanilla world changes stand in for player placements, without any gift event.
        c.command("fill 0 80 0 2 82 2 diamond_block")
        wait_for(lambda s: s["filled"] == 27 and s["defending"])
        c.command("setblock 1 82 1 air")
        wait_for(lambda s: s["filled"] == 26 and not s["defending"])
        assert not state()["wins"], "broken arena won"
        c.command("setblock 1 82 1 diamond_block")
        s = wait_for(lambda s: len(s["wins"]) == 1, 4)
        assert s["wins"][0]["win"] == 1, s
        wait_for(lambda s: s["filled"] == 0)
        c.command("lmsarena ack " + s["wins"][0]["eventId"])
        print("PASS world placement -> countdown, break cancellation, refill -> WIN and clear")

        generate(9)
        c.command("fill 0 80 0 8 80 8 diamond_block")
        wait_for(lambda s: s["filled"] == 81)
        c.command("summon tnt 4.5 81 4.5 {Fuse:1}")
        s = wait_for(lambda s: s["filled"] < 81)
        assert s["health"] == 20, "bottom layer must protect gauge from the same explosion"
        assert matches(4, 79, 4, "glass"), "TNT destroyed floor"
        c.command("summon tnt 4.5 80 4.5 {Fuse:1}")
        wait_for(lambda s: s["health"] == 10)
        c.command("summon tnt 4.5 80 4.5 {Fuse:1}")
        s = wait_for(lambda s: any(w["win"] == -3 for w in s["wins"]))
        assert s["health"] == 20, "gauge should reset after penalty"
        assert matches(4, 79, 4, "glass"), "floor must remain unbroken"
        for w in s["wins"]: c.command("lmsarena ack " + w["eventId"])
        print("PASS actual TNT: covered floor no damage; exposed floor damage; zero -> -WIN; frame survives")

        generate(9, floor=False)
        c.command("summon tnt 4.5 80 4.5 {Fuse:1}")
        time.sleep(.4)
        assert state()["health"] == 20 and not state()["wins"]
        c.command("lmsarena shield 1")
        c.command("fill 0 80 0 8 80 8 diamond_block")
        wait_for(lambda s: s["filled"] == 81)
        c.command("summon tnt 4.5 81 4.5 {Fuse:1}")
        s = wait_for(lambda s: s["shieldCharges"] == 0)
        assert s["filled"] == 81, s
        print("PASS floor rule OFF and actual explosion shield")


if __name__ == "__main__": run()
