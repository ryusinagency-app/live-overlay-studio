from __future__ import annotations

from pathlib import Path
from threading import Lock
import json
import hashlib
import os
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
import zipfile

from rcon import RconClient


PAPER_VERSION = "1.21.1"
PAPER_API = f"https://fill.papermc.io/v3/projects/paper/versions/{PAPER_VERSION}/builds"
JAVA_21_URL = "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse"
APP_USER_AGENT = "LiveMinecraftMountainStudio/0.3.0 (https://github.com/ryusinagency-app/live-overlay-studio)"


class LocalMinecraftServer:
    """Prepare and control a private Paper server on the same Windows PC."""

    def __init__(self, data_dir: Path):
        self.server_dir = data_dir / "mountain_server"
        self.jar_path = self.server_dir / "paper.jar"
        self.java_dir = data_dir / "java21"
        self.process: subprocess.Popen | None = None
        self.lock = Lock()
        self.message = "未準備"
        self._java = self.java_status()

    def java_executable(self) -> str:
        bundled = list(self.java_dir.glob("*/bin/java.exe")) + list(self.java_dir.glob("bin/java.exe"))
        if bundled:
            return str(bundled[0])
        return shutil.which("java") or "java"

    def java_status(self) -> dict:
        executable = self.java_executable()
        try:
            result = subprocess.run(
                [executable, "-version"], capture_output=True, text=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            text = (result.stderr or result.stdout or "").strip()
            version = text.splitlines()[0] if text else "Javaを確認できません"
            return {"available": result.returncode == 0, "version": version,
                    "bundled": str(executable).lower().startswith(str(self.java_dir).lower())}
        except Exception:
            return {"available": False, "version": "初回準備でJava 21を自動設定します", "bundled": False}

    def ensure_java(self) -> dict:
        current = self.java_status()
        if current["available"]:
            self._java = current
            return current
        self.java_dir.parent.mkdir(parents=True, exist_ok=True)
        archive = self.java_dir.parent / "java21.download"
        extract_dir = self.java_dir.parent / "java21.extracting"
        self.message = "アプリ専用Java 21をダウンロード中"
        try:
            request = urllib.request.Request(
                JAVA_21_URL,
                headers={
                    "User-Agent": APP_USER_AGENT,
                    "Accept": "application/octet-stream",
                },
            )
            with urllib.request.urlopen(request, timeout=180) as response, archive.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True)
            with zipfile.ZipFile(archive) as package:
                root = extract_dir.resolve()
                for member in package.infolist():
                    target = (extract_dir / member.filename).resolve()
                    if target != root and root not in target.parents:
                        raise RuntimeError("Javaファイルの展開先が不正です")
                package.extractall(extract_dir)
            if self.java_dir.exists():
                shutil.rmtree(self.java_dir)
            extract_dir.replace(self.java_dir)
        except Exception as exc:
            self.message = "Java 21の自動設定に失敗しました"
            raise RuntimeError(f"Java 21をダウンロードできませんでした: {exc}") from exc
        finally:
            archive.unlink(missing_ok=True)
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
        self._java = self.java_status()
        if not self._java["available"]:
            raise RuntimeError("アプリ専用Java 21を準備できませんでした")
        return self._java

    @staticmethod
    def _port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.35):
                return True
        except OSError:
            return False

    def status(self) -> dict:
        running = self._port_open(25566)
        return {
            "prepared": self.jar_path.exists(),
            "running": running,
            "serverDir": str(self.server_dir),
            "joinAddress": "localhost",
            "java": self._java,
            "message": self.message,
        }

    def install_plugin(self):
        root = Path(__file__).resolve().parent
        source = root / "LiveMinecraftMountain.jar"
        if not source.exists():
            source = root / "plugin" / "target" / "LiveMinecraftMountain.jar"
        if not source.exists():
            raise RuntimeError("ゲーム連携ファイルが見つかりません。アプリをダウンロードし直してください")
        destination = self.server_dir / "plugins" / "LiveMinecraftMountain.jar"
        if destination.exists() and hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(destination.read_bytes()).digest():
            return
        if self._port_open(25566):
            raise RuntimeError("ゲーム連携の更新には「安全に停止」→「サーバーを起動」が必要です")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)

    def prepare(self, eula_accepted: bool) -> dict:
        if not eula_accepted:
            raise ValueError("Minecraft EULAへの同意にチェックしてください")
        self.ensure_java()

        with self.lock:
            self.server_dir.mkdir(parents=True, exist_ok=True)
            self.message = "Paper 1.21.1を準備中"
            if not self.jar_path.exists():
                temporary = self.jar_path.with_suffix(".download")
                try:
                    request = urllib.request.Request(
                        PAPER_API,
                        headers={"User-Agent": APP_USER_AGENT, "Accept": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=30) as response:
                        builds = json.load(response)
                    stable = next(
                        (item for item in builds if str(item.get("channel", "")).upper() == "STABLE"),
                        None,
                    )
                    download = (stable or {}).get("downloads", {}).get("server:default", {})
                    url = download.get("url")
                    if not url:
                        raise RuntimeError("安定版のダウンロード情報が見つかりません")
                    self.message = "Paper 1.21.1をダウンロード中"
                    download_request = urllib.request.Request(
                        url,
                        headers={"User-Agent": APP_USER_AGENT, "Accept": "application/java-archive"},
                    )
                    with urllib.request.urlopen(download_request, timeout=180) as response, temporary.open("wb") as output:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                    if temporary.stat().st_size < 1_000_000:
                        raise RuntimeError("ダウンロードしたPaperファイルが不完全です")
                    temporary.replace(self.jar_path)
                except Exception as exc:
                    self.message = "Paper 1.21.1の準備に失敗しました"
                    raise RuntimeError(f"Paper 1.21.1をダウンロードできませんでした: {exc}") from exc
                finally:
                    temporary.unlink(missing_ok=True)

            password = secrets.token_urlsafe(24)
            (self.server_dir / "eula.txt").write_text("eula=true\n", "utf-8")
            properties = {
                "server-port": "25566",
                "server-ip": "",
                "online-mode": "true",
                "gamemode": "adventure",
                "difficulty": "normal",
                "max-players": "2",
                "spawn-protection": "0",
                "view-distance": "10",
                "simulation-distance": "8",
                "enable-rcon": "true",
                "rcon.port": "25576",
                "rcon.password": password,
                "broadcast-rcon-to-ops": "false",
                "motd": "Live Minecraft Mountain Studio",
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
        self.install_plugin()
        if self._port_open(25566):
            self.message = "サーバーは起動済みです"
            return self.status()
        self.ensure_java()
        log = (self.server_dir / "live_minecraft_server.log").open("a", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [self.java_executable(), "-Xms2G", "-Xmx6G", "-jar", str(self.jar_path), "--nogui"],
            cwd=self.server_dir, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        self.message = "起動中"
        deadline = time.time() + 90
        while time.time() < deadline:
            if self._port_open(25566):
                self.message = "起動しました。Minecraftから localhost で参加できます"
                return self.status()
            if self.process.poll() is not None:
                self.message = "起動に失敗しました"
                raise RuntimeError("Minecraftサーバーを起動できませんでした。サーバーログを確認してください")
            time.sleep(0.5)
        raise RuntimeError("起動完了を確認できませんでした")

    def stop(self, rcon: dict) -> dict:
        if not self._port_open(25566):
            self.message = "停止中"
            return self.status()
        try:
            with RconClient("127.0.0.1", int(rcon.get("port", 25576)), str(rcon.get("password", ""))) as client:
                client.command("save-all flush")
                client.command("stop")
        except Exception as exc:
            raise RuntimeError(f"安全に停止できませんでした: {exc}") from exc
        deadline = time.time() + 30
        while time.time() < deadline and self._port_open(25566):
            time.sleep(0.5)
        self.message = "安全に停止しました"
        return self.status()


