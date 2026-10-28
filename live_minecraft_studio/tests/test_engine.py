import unittest
from game_engine import Arena, GameEngine, MultiplierState
from server import classify_server_software


class EngineTests(unittest.TestCase):
    def engine(self):
        return GameEngine(Arena(width=3, depth=3, height=3, hold_seconds=10),
                          MultiplierState(threshold=5000, duration_seconds=300, multiplier=2))

    def test_multiplier_activates_and_doubles_fill(self):
        e = self.engine()
        effects = {"fill": {"name": "埋める", "kind": "fill", "amount": 2}}
        result = e.receive({"eventId": "1", "giftId": "fill", "coins": 5000}, effects)
        self.assertEqual(4, len(e.arena.filled))
        self.assertLessEqual(len(result["commands"]), 4)
        self.assertTrue(e.multiplier.active())

    def test_duplicate_event_is_ignored(self):
        e = self.engine(); effects = {"fill": {"kind": "fill", "amount": 1}}
        e.receive({"eventId": "same", "giftId": "fill"}, effects)
        result = e.receive({"eventId": "same", "giftId": "fill"}, effects)
        self.assertTrue(result["duplicate"])
        self.assertEqual(1, len(e.arena.filled))

    def test_full_arena_starts_countdown_and_awards_after_hold(self):
        e = self.engine(); effects = {"all": {"kind": "fill_all", "amount": 1}}
        e.receive({"eventId": "full", "giftId": "all"}, effects)
        started = e.arena.full_since
        self.assertIsNone(e.tick(started + 9.9))
        result = e.tick(started + 10)
        self.assertEqual(1, result["win"])
        self.assertEqual(0, len(e.arena.filled))

    def test_break_resets_countdown(self):
        e = self.engine(); effects = {
            "all": {"kind": "fill_all", "amount": 1},
            "tnt": {"kind": "tnt", "amount": 1, "breakBlocks": 1},
        }
        e.receive({"eventId": "full", "giftId": "all"}, effects)
        e.receive({"eventId": "boom", "giftId": "tnt"}, effects)
        self.assertEqual(0, e.arena.full_since)
        self.assertEqual(26, len(e.arena.filled))

    def test_shield_prevents_break_and_keeps_countdown(self):
        e = self.engine(); effects = {
            "all": {"kind": "fill_all", "amount": 1},
            "shield": {"kind": "shield", "amount": 1},
            "tnt": {"kind": "tnt", "amount": 1, "breakBlocks": 1},
        }
        e.receive({"eventId": "full", "giftId": "all"}, effects)
        started = e.arena.full_since
        e.receive({"eventId": "shield", "giftId": "shield"}, effects)
        e.receive({"eventId": "boom", "giftId": "tnt"}, effects)
        self.assertEqual(started, e.arena.full_since)
        self.assertEqual(27, len(e.arena.filled))
        self.assertEqual(0, e.arena.shield_charges)

    def test_gifts_can_change_countdown(self):
        e = self.engine(); effects = {
            "all": {"kind": "fill_all", "amount": 1},
            "plus": {"kind": "countdown", "countdownMode": "add", "seconds": 5},
            "minus": {"kind": "countdown", "countdownMode": "add", "seconds": -3},
            "set": {"kind": "countdown", "countdownMode": "set", "seconds": 4},
        }
        e.receive({"eventId": "full", "giftId": "all"}, effects)
        started = e.arena.full_since
        e.receive({"eventId": "plus", "giftId": "plus"}, effects)
        self.assertEqual(started + 5, e.arena.full_since)
        e.receive({"eventId": "minus", "giftId": "minus"}, effects)
        self.assertEqual(started + 2, e.arena.full_since)
        e.receive({"eventId": "set", "giftId": "set"}, effects)
        remaining = e.arena.hold_seconds - (__import__('time').time() - e.arena.full_since)
        self.assertAlmostEqual(4, remaining, delta=.1)

    def test_server_software_detection(self):
        self.assertEqual("Paper系", classify_server_software("This server is running Paper version 1.21"))
        self.assertEqual("Fabric系", classify_server_software("fabric-loader 0.16"))
        self.assertEqual("バニラ／判定不能", classify_server_software("Unknown command"))


if __name__ == "__main__":
    unittest.main()
