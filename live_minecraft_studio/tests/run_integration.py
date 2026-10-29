"""Launch only a separately prepared, disposable Paper server for integration checks."""
import os
from pathlib import Path
import socket
import subprocess
import time
from integration_server import run


folder = Path(os.environ["LMS_TEST_SERVER_DIR"]).resolve()
if folder == Path.cwd() or "lms-integration" not in folder.name:
    raise RuntimeError("Use an explicitly prepared disposable lms-integration directory")
process = subprocess.Popen([os.environ["LMS_TEST_JAVA"], "-Xms512M", "-Xmx1536M", "-jar", "paper.jar", "--nogui"],
                           cwd=folder, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
try:
    for _ in range(150):
        if process.poll() is not None: raise RuntimeError("Paper failed to start")
        try:
            with socket.create_connection(("127.0.0.1", 25595), .2): break
        except OSError: time.sleep(.2)
    else: raise RuntimeError("Paper did not become ready")
    run()
    if os.environ.get("LMS_TEST_BOT_SCRIPT"):
        subprocess.run(["node", os.environ["LMS_TEST_BOT_SCRIPT"]], check=True)
finally:
    process.communicate(b"stop\n", timeout=30)
