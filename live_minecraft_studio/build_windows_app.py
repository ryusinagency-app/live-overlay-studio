from pathlib import Path
import PyInstaller.__main__


root = Path(__file__).resolve().parent
PyInstaller.__main__.run([
    str(root / "launcher.py"),
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "Live_Minecraft_Studio_Windows_x64",
    "--distpath", str(root / "dist"),
    "--workpath", str(root / "build"),
    "--specpath", str(root),
    "--add-data", f"{root / 'index.html'};.",
    "--add-data", f"{root / 'overlay.html'};.",
    "--add-data", f"{root / 'effects_overlay.html'};.",
    "--add-data", f"{root / 'app.js'};.",
    "--add-data", f"{root / 'style.css'};.",
])
