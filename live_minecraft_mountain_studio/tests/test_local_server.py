import tempfile, unittest
from pathlib import Path
from local_server import LocalMinecraftServer

class LocalServerTests(unittest.TestCase):
    def test_dedicated_paths_and_ports(self):
        with tempfile.TemporaryDirectory() as d:
            s=LocalMinecraftServer(Path(d))
            self.assertEqual("mountain_server",s.server_dir.name)
            self.assertEqual("localhost",s.status()["joinAddress"])
    def test_eula_required(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): LocalMinecraftServer(Path(d)).prepare(False)

if __name__ == '__main__': unittest.main()

