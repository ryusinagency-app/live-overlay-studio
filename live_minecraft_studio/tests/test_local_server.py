from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io
import unittest
import zipfile

from local_server import APP_USER_AGENT, LocalMinecraftServer, PAPER_API


class LocalServerTests(unittest.TestCase):
    def test_plugin_update_preserves_world_and_other_plugins(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "app" / "LiveMinecraftArena.jar"
            source.parent.mkdir()
            source.write_bytes(b"new bridge")
            server = LocalMinecraftServer(base / "data")
            server._port_open = lambda _: False
            plugins = server.server_dir / "plugins"
            plugins.mkdir(parents=True)
            (plugins / "Other.jar").write_bytes(b"keep")
            (plugins / "LiveMinecraftArena.jar").write_bytes(b"old bridge")
            with patch("local_server.__file__", str(source.parent / "local_server.py")):
                server.install_plugin()
            self.assertEqual(b"new bridge", (plugins / "LiveMinecraftArena.jar").read_bytes())
            self.assertEqual(b"keep", (plugins / "Other.jar").read_bytes())

    def test_running_server_requires_restart_for_bridge_update(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "LiveMinecraftArena.jar").write_bytes(b"bridge")
            server = LocalMinecraftServer(base / "data")
            server._port_open = lambda _: True
            with patch("local_server.__file__", str(base / "local_server.py")):
                with self.assertRaisesRegex(RuntimeError, "安全に停止"):
                    server.install_plugin()

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

    def test_java_download_identifies_the_app_to_avoid_403(self):
        with TemporaryDirectory() as folder:
            server = LocalMinecraftServer(Path(folder))
            statuses = iter([
                {"available": False, "version": "未設定", "bundled": False},
                {"available": True, "version": 'openjdk version "21"', "bundled": True},
            ])
            server.java_status = lambda: next(statuses)
            package = io.BytesIO()
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("jdk-21/bin/java.exe", b"test")
            package.seek(0)
            seen = {}

            class Response(io.BytesIO):
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.close()

            def fake_open(request, timeout=0):
                seen["user_agent"] = request.get_header("User-agent")
                seen["accept"] = request.get_header("Accept")
                return Response(package.getvalue())

            with patch("urllib.request.urlopen", fake_open):
                result = server.ensure_java()

            self.assertTrue(result["available"])
            self.assertEqual(seen["user_agent"], APP_USER_AGENT)
            self.assertEqual(seen["accept"], "application/octet-stream")
            self.assertTrue(any(server.java_dir.glob("*/bin/java.exe")))

    def test_paper_download_uses_v3_api_and_required_user_agent(self):
        with TemporaryDirectory() as folder:
            server = LocalMinecraftServer(Path(folder))
            server.java_status = lambda: {"available": True, "version": 'openjdk version "21"', "bundled": True}
            seen = []

            class Response(io.BytesIO):
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    self.close()

            builds = b'[{"id":123,"channel":"STABLE","downloads":{"server:default":{"url":"https://example.test/paper.jar"}}}]'

            def fake_open(request, timeout=0):
                seen.append((request.full_url, request.get_header("User-agent")))
                if request.full_url == PAPER_API:
                    return Response(builds)
                return Response(b"paper" * 250000)

            with patch("urllib.request.urlopen", fake_open):
                result = server.prepare(True)

            self.assertTrue(result["prepared"])
            self.assertEqual(seen[0], (PAPER_API, APP_USER_AGENT))
            self.assertEqual(seen[1], ("https://example.test/paper.jar", APP_USER_AGENT))


if __name__ == "__main__":
    unittest.main()

