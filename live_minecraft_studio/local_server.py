from __future__ import annotations

from pathlib import Path
from threading import Lock
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request

from rcon import RconClient


PAPER_VERSION = "1.21.1"
PAPER_API = f"https://api.papermc.io/v2/projects/paper/versions/{PAPER_VERSION}"


class LocalMinecraftServer:
    """Prepare and control a private Paper server on the same Windows PC."""

    def __init__(self, data_dir: Path):
        self.server_dir = data_dir / "minecraft_server"
        self.jar_path = self.server_dir / "paper.jar"
        self.process: subprocess.Popen | None = None
        self.lock = Lock()
        self.message = "未準備"

    @staticmethod
    def java_status() -> dict:
        try:
            result = subprocess.run(
                ["java", "-version"], capture_output=True, text=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            text = (result.stderr or result.stdout or "").strip()
            version = text.splitlines()[0] if text else "Javaを確認できません"
            return {"available": result.returncode == 0, "version": version}
        except Exception:
            return {"available": False, "version": "Java 21が必要です"}

    @staticmethod
    def _port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.35):
                return True
        except OSError:
            return False

    def status(self) -> dict:
        running = self._port_open(25565)
        return {
            "prepared": self.jar_path.exists(),
            "running": running,
            "serverDir": str(self.server_dir),
            "joinAddress": "localhost",
            "java": self.java_status(),
            "message": self.message,
        }

    def prepare(self, eula_accepted: bool) -> dict:
        if not eula_accepted:
            raise ValueError("Minecraft EULAへの同意にチェックしてください")
        java = self.java_status()
        if not java["available"]:
            raise RuntimeError("Java 21が見つかりません。Java 21をインストールしてから、もう一度押してください")

        with self.lock:
            self.server_dir.mkdir(parents=True, exist_ok=True)
            self.message = "Paper 1.21.1を準備中"
            if not self.jar_path.exists():
                with urllib.request.urlopen(PAPER_API + "/builds", timeout=30) as response:
                    payload = json.load(response)
                builds = payload.get("builds") or []
                if not builds:
                    raise RuntimeError("Paper 1.21.1のダウンロード情報を取得できませんでした")
                latest = max(int(item["build"]) for item in builds if item.get("channel") == "default")
                name = f"paper-{PAPER_VERSION}-{latest}.jar"
                url = f"{PAPER_API}/builds/{latest}/downloads/{name}"
                temporary = self.jar_path.with_suffix(".download")
                with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                temporary.replace(self.jar_path)

            password = secrets.token_urlsafe(24)
            (self.server_dir / "eula.txt").write_text("eula=true\n", "utf-8")
            properties = {
                "server-port": "25565",
                "server-ip": "",
                "online-mode": "true",
                "gamemode": "creative",
                "difficulty": "normal",
                "max-players": "2",
                "spawn-protection": "0",
                "view-distance": "10",
                "simulation-distance": "8",
                "enable-rcon": "true",
                "rcon.port": "25575",
                "rcon.password": password,
                "broadcast-rcon-to-ops": "false",
                "motd": "Live Minecraft Studio",
            }
            existing = {}
            properties_file = self.server_dir / "server.properties"
            if properties_file.exists():
                for line in properties_file.read_text("utf-8", errors="ignore").splitlines():
                    if "=" in line and not line.lstrip().startswith("#"):
                        key, value = line.split("=", 1)
                        existing[key] = value
            existing.update(properties)
            properties_file.write_text(
                "\n".join(f"{key}={value}" for key, value in existing.items()) + "\n", "utf-8"
            )
            self.message = "準備完了"
            return {"password": password, **self.status()}

    def start(self) -> dict:
        if not self.jar_path.exists():
            raise RuntimeError("先に「サーバーを準備」を押してください")
        if self._port_open(25565):
            self.message = "サーバーは起動済みです"
            return self.status()
        java = self.java_status()
        if not java["available"]:
            raise RuntimeError("Java 21が見つかりません")
        log = (self.server_dir / "live_minecraft_server.log").open("a", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            ["java", "-Xms2G", "-Xmx6G", "-jar", str(self.jar_path), "--nogui"],
            cwd=self.server_dir, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        self.message = "起動中"
        deadline = time.time() + 90
        while time.time() < deadline:
            if self._port_open(25565):
                self.message = "起動しました。Minecraftから localhost で参加できます"
                return self.status()
            if self.process.poll() is not None:
                self.message = "起動に失敗しました"
                raise RuntimeError("Minecraftサーバーを起動できませんでした。サーバーログを確認してください")
            time.sleep(0.5)
        raise RuntimeError("起動完了を確認できませんでした")

    def stop(self, rcon: dict) -> dict:
        if not self._port_open(25565):
            self.message = "停止中"
            return self.status()
        try:
            with RconClient("127.0.0.1", int(rcon.get("port", 25575)), str(rcon.get("password", ""))) as client:
                client.command("save-all flush")
                client.command("stop")
        except Exception as exc:
            raise RuntimeError(f"安全に停止できませんでした: {exc}") from exc
        deadline = time.time() + 30
        while time.time() < deadline and self._port_open(25565):
            time.sleep(0.5)
        self.message = "安全に停止しました"
        return self.status()
