from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from local_server import LocalMinecraftServer


class LocalServerTests(unittest.TestCase):
    def test_prepare_requires_eula_and_writes_private_server_settings(self):
        with TemporaryDirectory() as folder:
            server = LocalMinecraftServer(Path(folder))
            server.java_status = lambda: {"available": True, "version": 'openjdk version "21"'}
            server.server_dir.mkdir(parents=True)
            server.jar_path.write_bytes(b"test")

            with self.assertRaises(ValueError):
                server.prepare(False)

            result = server.prepare(True)
            properties = (server.server_dir / "server.properties").read_text("utf-8")
            self.assertTrue(result["prepared"])
            self.assertEqual(result["joinAddress"], "localhost")
            self.assertIn("enable-rcon=true", properties)
            self.assertIn("rcon.port=25575", properties)
            self.assertIn("server-port=25565", properties)
            self.assertIn("server-ip=\n", properties)
            self.assertIn("eula=true", (server.server_dir / "eula.txt").read_text("utf-8"))
            self.assertTrue(result["password"])


if __name__ == "__main__":
    unittest.main()
