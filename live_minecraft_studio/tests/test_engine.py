import unittest
from unittest.mock import patch
import server
from game_engine import Arena, GameEngine, MultiplierState
from server import bridge_command, classify_server_software, effect_preview_label, receive_social


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

    def test_fill_all_uses_safe_server_effect(self):
        e = self.engine()
        result = e.receive({"eventId": "all", "giftId": "all"},
                           {"all": {"kind": "fill_all", "amount": 1}})
        self.assertEqual("lmsarena fill_all", result["commands"][0])

    def test_gift_sound_event_works_without_visible_message(self):
        e = self.engine()
        effect = {"sound": {"kind": "fill", "amount": 1, "displayEnabled": False,
                            "soundEnabled": True, "soundUrl": "/user-sounds/test.mp3",
                            "soundVolume": 35, "soundSeconds": 2.5}}
        result = e.receive({"eventId": "sound-only", "giftId": "sound"}, effect)
        self.assertEqual(["lmsarena fill 1"], result["commands"])
        notice = e.snapshot()["announcements"][-1]
        self.assertFalse(notice["display"])
        self.assertEqual("/user-sounds/test.mp3", notice["soundUrl"])
        self.assertEqual(35, notice["soundVolume"])
        self.assertEqual(2.5, notice["soundSeconds"])

    def test_external_sound_url_is_not_forwarded_to_overlay(self):
        e = self.engine()
        effect = {"sound": {"kind": "fill", "amount": 1, "displayEnabled": False,
                            "soundEnabled": True, "soundUrl": "https://example.invalid/x.mp3"}}
        e.receive({"eventId": "external-sound", "giftId": "sound"}, effect)
        self.assertEqual([], e.snapshot()["announcements"])

    def test_one_gift_can_apply_multiple_effects_once_each(self):
        e = self.engine()
        effect = {"combo": {"name": "複合ギフト", "kind": "fill", "amount": 4, "win": 1,
                            "additionalEffects": [
                                {"kind": "tnt", "amount": 2, "tntType": "piercing", "win": -1},
                                {"kind": "freeze", "seconds": 3, "win": 0}
                            ]}}
        result = e.receive({"eventId": "combo", "giftId": "combo"}, effect)
        self.assertEqual(["lmsarena fill 4", "lmsarena tnt 2 piercing 60", "lmsarena freeze 3"], result["commands"][:3])
        self.assertEqual(0, result["win"])
        self.assertEqual(3, len(result["effects"]))
        self.assertIn("4ブロック", e.snapshot()["announcements"][-1]["text"])
        self.assertIn("TNT×2", e.snapshot()["announcements"][-1]["text"])

    def test_gacha_only_effect_does_not_fire_as_a_normal_gift(self):
        e = self.engine()
        effects = {"prize": {"kind": "tnt", "amount": 10, "gachaOnly": True}}
        normal = e.receive({"eventId": "normal", "giftId": "prize"}, effects)
        prize = e.receive({"eventId": "prize", "giftId": "prize", "source": "gacha"}, effects)
        self.assertEqual([], normal["commands"])
        self.assertEqual("lmsarena tnt 10 normal 60", prize["commands"][0])

    def test_blank_display_text_can_disable_automatic_effect_text(self):
        e = self.engine()
        effects = {"quiet": {"kind": "fill", "amount": 5, "displayText": "", "autoDisplayText": False}}
        result = e.receive({"eventId": "quiet", "giftId": "quiet", "senderName": "視聴者"}, effects)
        self.assertFalse(e.snapshot()["announcements"])
        self.assertFalse(any(command.startswith("lmsarena announce ") for command in result["commands"]))

    def test_disabled_effect_never_fires(self):
        e = self.engine()
        result = e.receive({"eventId": "disabled", "giftId": "off", "source": "social"},
                           {"off": {"kind": "fill_all", "enabled": False}})
        self.assertEqual([], result["commands"])

    def test_gift_effect_can_be_limited_to_one_user_id(self):
        effect = {"only": {"kind": "fill", "amount": 3, "allowedGiftUserId": "@ryusin__ch"}}
        blocked = self.engine().receive({"eventId": "blocked", "giftId": "only", "source": "gift",
                                         "uniqueId": "someone_else"}, effect)
        allowed = self.engine().receive({"eventId": "allowed", "giftId": "only", "source": "gift",
                                         "uniqueId": "RYUSIN__CH"}, effect)
        self.assertEqual([], blocked["commands"])
        self.assertTrue(allowed["commands"])

    def test_gift_user_filter_accepts_nested_tiktok_user(self):
        effects = {"only": {"kind": "fill", "amount": 3, "allowedGiftUserId": "@viewer_01"}}
        result = self.engine().receive(
            {"eventId": "nested-user", "giftId": "only", "source": "gift",
             "user": {"uniqueId": "Viewer_01"}}, effects)
        self.assertEqual("lmsarena fill 3", result["commands"][0])

    def test_new_player_effect_commands(self):
        engine = self.engine()
        darkness = engine.receive({"eventId": "dark", "giftId": "dark"},
                                  {"dark": {"kind": "darkness", "seconds": 7}})
        enderman = engine.receive({"eventId": "ender", "giftId": "ender"},
                                  {"ender": {"kind": "enderman", "amount": 4}})
        self.assertEqual("lmsarena darkness 7", darkness["commands"][0])
        self.assertEqual("lmsarena enderman 4", enderman["commands"][0])

    def test_disabled_multiplier_does_not_count_or_activate(self):
        multiplier = MultiplierState(enabled=False, threshold=100)
        self.assertEqual(0, multiplier.add_coins(500))
        self.assertEqual(0, multiplier.total_coins)
        self.assertFalse(multiplier.active())
        self.assertEqual(1, multiplier.factor("fill"))

    def test_coin_value_starts_fever_and_scales_the_triggering_effect(self):
        engine = GameEngine(Arena(width=3, depth=3, height=3),
                            MultiplierState(threshold=100, next_target=100, multiplier=2, duration_seconds=60))
        result = engine.receive({"eventId": "fever", "giftId": "fill", "coinValue": 100},
                                {"fill": {"kind": "fill", "amount": 3, "useMultiplier": True}})
        self.assertTrue(engine.multiplier.active())
        self.assertEqual(1, result["multiplierActivations"])
        self.assertEqual(6, result["effects"][0]["amount"])

    def test_display_text_is_used_for_effect_list_preview_with_additional_effects(self):
        effect = {"name": "複合ギフト", "displayText": "発動：{effects}", "kind": "fill", "amount": 10,
                  "additionalEffects": [{"kind": "tnt", "amount": 3}]}
        actions = [
            {"effectiveLabel": "10ブロック", "amount": 10, "seconds": 0, "strength": 0, "resizeDelta": 0},
            {"effectiveLabel": "TNT×3", "amount": 3, "seconds": 0, "strength": 0, "resizeDelta": 0},
        ]
        self.assertEqual("発動：10ブロック ＋ TNT×3", effect_preview_label(effect, actions))

    def test_follow_and_likes_trigger_each_effect_and_gacha_directly(self):
        with server.STATE_LOCK:
            original = {key: server.STATE.get(key) for key in ("effects", "gachas", "socialRuntime")}
            server.STATE["effects"] = {"help": {"enabled": True, "followTriggerEnabled": True,
                                                  "individualLikeTriggerEnabled": True, "individualLikeEvery": 10}}
            server.STATE["gachas"] = {"chaos": {"enabled": True, "followTriggerEnabled": True,
                                                   "totalLikeTriggerEnabled": True, "totalLikeEvery": 20}}
            server.STATE["socialRuntime"] = {"followedUsers": [], "individualLikes": {}, "totalLikes": 0}
        try:
            with patch.object(server, "trigger_target") as trigger, patch.object(server, "save_state"):
                first = receive_social({"type": "follow", "userId": "u1", "userName": "配信者"})
                self.assertEqual(2, first["triggered"])
                self.assertEqual({"effect:help", "gacha:chaos"}, {call.args[0] for call in trigger.call_args_list})
                trigger.reset_mock()
                likes = receive_social({"type": "like", "userId": "u1", "count": 20})
                self.assertEqual(3, likes["triggered"])
                self.assertEqual(3, trigger.call_count)
        finally:
            with server.STATE_LOCK:
                for key, value in original.items(): server.STATE[key] = value

    def test_social_accepts_tiktok_event_names_and_nested_users(self):
        old_effects = server.STATE.get("effects")
        old_gachas = server.STATE.get("gachas")
        old_runtime = server.STATE.get("socialRuntime")
        try:
            server.STATE["effects"] = {
                "follow": {"enabled": True, "followTriggerEnabled": True},
                "likes": {"enabled": True, "individualLikeTriggerEnabled": True, "individualLikeEvery": 5},
            }
            server.STATE["gachas"] = {}
            server.STATE["socialRuntime"] = {"followedUsers": [], "individualLikes": {}, "totalLikes": 0}
            with patch.object(server, "trigger_target", return_value=True):
                follow = receive_social({"eventName": "FollowEvent", "user": {"uniqueId": "viewer1", "nickname": "視聴者"}})
                likes = receive_social({"event": "like_event", "user": {"uniqueId": "viewer1"}, "likeCount": 5})
            self.assertEqual(1, follow["triggered"])
            self.assertEqual(1, likes["triggered"])
            self.assertEqual(5, likes["totalLikes"])
        finally:
            server.STATE["effects"] = old_effects
            server.STATE["gachas"] = old_gachas
            server.STATE["socialRuntime"] = old_runtime

    def test_direct_gacha_uses_repeat_count_and_user_filter(self):
        old_gachas = server.STATE.get("gachas")
        try:
            server.STATE["gachas"] = {
                "vip": {"enabled": True, "triggerGiftId": "rose", "allowedGiftUserId": "@ryusin__ch"}
            }
            with patch.object(server, "start_gacha", return_value=True) as start:
                blocked = server.trigger_gachas_for_gift(
                    {"giftId": "rose", "uniqueId": "someone", "repeatCount": 5}, "blocked")
                allowed = server.trigger_gachas_for_gift(
                    {"giftId": "rose", "uniqueId": "RYUSIN__CH", "repeatCount": 5,
                     "senderName": "りゅーしん"}, "allowed")
            self.assertEqual(0, blocked)
            self.assertEqual(5, allowed)
            start.assert_called_once_with("vip", "りゅーしん", "allowed-direct-vip", 5)
        finally:
            server.STATE["gachas"] = old_gachas

    def test_frame_is_atomic_with_optional_floor(self):
        e = self.engine()
        self.assertEqual(1, len(e.frame_commands()))
        self.assertIn("lmsarena generate world", e.frame_commands()[0])
        self.assertTrue(e.frame_commands()[0].endswith("false 100 10 1 3 64 3 64 false false"))
        e.arena.floor_enabled = True
        self.assertTrue(e.frame_commands()[0].endswith("true 100 10 1 3 64 3 64 false false"))

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

