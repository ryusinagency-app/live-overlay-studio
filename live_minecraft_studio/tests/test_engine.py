import unittest
from game_engine import Arena, GameEngine, MultiplierState
from server import bridge_command, classify_server_software


class EngineTests(unittest.TestCase):
    def engine(self):
        return GameEngine(Arena(width=3, depth=3, height=3), MultiplierState())

    def test_gift_is_intent_not_fictitious_world_state(self):
        e = self.engine()
        r = e.receive({"eventId": "gift", "giftId": "fill", "coins": 5000}, {"fill": {"kind": "fill", "amount": 2}})
        self.assertEqual("lmsarena fill 4", r["commands"][0])
        self.assertTrue(r["commands"][1].startswith("lmsarena announce "))
        self.assertEqual(0, e.snapshot()["arena"]["filled"])
        self.assertIsNone(e.tick())

    def test_manual_world_counts_and_server_countdown_are_used(self):
        e = self.engine()
        e.sync_world({"ready": True, "filled": 27, "capacity": 27, "defending": True, "holdRemainingSeconds": 6})
        self.assertEqual(27, e.snapshot()["arena"]["filled"])
        self.assertEqual(6, e.snapshot()["arena"]["holdRemainingSeconds"])
        e.sync_world({"ready": True, "filled": 26, "capacity": 27, "defending": False})
        self.assertFalse(e.snapshot()["arena"]["defending"])

    def test_server_win_delivered_once_and_penalty_is_distinct(self):
        e = self.engine()
        state = {"wins": [{"eventId": "win-1", "win": 1}, {"eventId": "floor-1", "win": -5, "reason": "底の耐久ゼロ"}]}
        events = e.sync_world(state)
        self.assertEqual([1, -5], [v["win"] for v in events])
        self.assertEqual("底の耐久ゼロ", events[1]["message"])
        self.assertEqual([], e.sync_world(state))

    def test_duplicate_gift_not_sent_twice(self):
        e = self.engine()
        effect = {"fill": {"kind": "fill", "amount": 1}}
        payload = {"eventId": "same", "giftId": "fill"}
        e.receive(payload, effect)
        self.assertTrue(e.receive(payload, effect)["duplicate"])

    def test_tnt_never_invents_breakage_or_damage(self):
        e = self.engine()
        e.sync_world({"filled": 27, "capacity": 27, "health": 100})
        r = e.receive({"eventId": "tnt", "giftId": "tnt"}, {"tnt": {"kind": "tnt", "amount": 1, "damage": 1000, "breakWin": -100}})
        self.assertEqual("lmsarena tnt 1 normal 60", r["commands"][0])
        self.assertEqual(0, r["win"])
        self.assertEqual(27, e.snapshot()["arena"]["filled"])
        self.assertEqual(100, e.snapshot()["arena"]["health"])

    def test_fill_layers_and_percent_are_server_authoritative(self):
        e = self.engine()
        layers = e.receive({"eventId": "layers", "giftId": "layers"},
                           {"layers": {"kind": "fill_layers", "amount": 2}})
        percent = e.receive({"eventId": "half", "giftId": "half"},
                            {"half": {"kind": "fill_percent", "amount": 50}})
        self.assertEqual("lmsarena fill_layers 2", layers["commands"][0])
        self.assertEqual("lmsarena fill_percent 50", percent["commands"][0])
        self.assertEqual(0, e.snapshot()["arena"]["filled"])

    def test_frame_is_atomic_with_optional_floor(self):
        e = self.engine()
        self.assertEqual(1, len(e.frame_commands()))
        self.assertIn("lmsarena generate world", e.frame_commands()[0])
        self.assertTrue(e.frame_commands()[0].endswith("false 100 10 1 3 64 3 64"))
        e.arena.floor_enabled = True
        self.assertTrue(e.frame_commands()[0].endswith("true 100 10 1 3 64 3 64"))

    def test_missing_plugin_and_server_error_not_reported_as_success(self):
        class Client:
            def __init__(self, reply): self.reply = reply
            def command(self, _): return self.reply
        with self.assertRaises(RuntimeError): bridge_command(Client("Unknown command"), "lmsarena status")
        with self.assertRaisesRegex(RuntimeError, "bad block"): bridge_command(Client('{"ok":false,"message":"bad block"}'), "lmsarena generate")
        self.assertEqual({"ok": True}, bridge_command(Client('{"ok":true}'), "lmsarena status"))

    def test_server_software_detection(self):
        self.assertEqual("Paper系", classify_server_software("This server is running Paper version 1.21"))
        self.assertEqual("Fabric系", classify_server_software("fabric-loader 0.16"))


if __name__ == "__main__":
    unittest.main()

