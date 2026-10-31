import unittest
from game_engine import Course, GameEngine, MultiplierState

class EngineTests(unittest.TestCase):
    def test_configure_command(self):
        e=GameEngine(Course(goal_y=200, goal_radius=5, checkpoint_rise=25, goal_win=2))
        self.assertEqual("lmsmountain configure world 0 64 0 0 200 0 5 25 2", e.configure_command())
    def test_multiple_actions_and_multiplier(self):
        m=MultiplierState(True,100,300,2); m.add_coins(100)
        e=GameEngine(multiplier=m)
        r=e.receive({"name":"妨害","actions":[{"kind":"tnt","amount":3},{"kind":"zombie","amount":2}]},"viewer")
        self.assertEqual(["lmsmountain effect tnt 6","lmsmountain effect zombie 4"],r["commands"])
        self.assertEqual("viewer",r["announcement"]["sender"])
    def test_world_status_is_exposed(self):
        e=GameEngine();e.update_world({"active":True,"players":[{"y":80}]})
        self.assertTrue(e.snapshot()["course"]["active"])

if __name__ == '__main__': unittest.main()

