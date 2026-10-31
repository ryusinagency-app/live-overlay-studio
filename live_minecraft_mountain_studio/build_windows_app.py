from pathlib import Path
import PyInstaller.__main__


root = Path(__file__).resolve().parent
bridge = root / "plugin" / "target" / "LiveMinecraftMountain.jar"
if not bridge.exists():
    raise RuntimeError("先に plugin ディレクトリで mvn package を実行してください")
PyInstaller.__main__.run([
    str(root / "launcher.py"),
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "Live_Minecraft_Mountain_Studio_Windows_x64",
    "--distpath", str(root / "dist"),
    "--workpath", str(root / "build"),
    "--specpath", str(root),
    "--add-data", f"{root / 'index.html'};.",
    "--add-data", f"{root / 'overlay.html'};.",
    "--add-data", f"{root / 'gacha_overlay.html'};.",
    "--add-data", f"{root / 'app.js'};.",
    "--add-data", f"{root / 'style.css'};.",
    "--add-data", f"{bridge};.",
])
