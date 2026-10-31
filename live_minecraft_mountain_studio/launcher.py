from __future__ import annotations

from threading import Thread
import tkinter as tk
import webbrowser

import server


def main():
    httpd = server.make_server()
    Thread(target=httpd.serve_forever, daemon=True).start()
    root = tk.Tk()
    root.title("Live Minecraft Mountain Studio")
    root.geometry("460x330")
    root.configure(bg="#11141b")
    root.resizable(False, False)
    tk.Label(root, text="Live Minecraft Mountain Studio", fg="white", bg="#11141b",
             font=("Yu Gothic UI", 22, "bold")).pack(pady=(35, 8))
    tk.Label(root, text=f"山登り妨害ゲーム  v{server.APP_VERSION}", fg="#aab0bf", bg="#11141b",
             font=("Yu Gothic UI", 11)).pack()
    tk.Button(root, text="操作画面を開く", command=lambda: webbrowser.open("http://127.0.0.1:8776/"),
              bg="#ef334e", fg="white", activebackground="#d92540", relief="flat",
              font=("Yu Gothic UI", 13, "bold"), width=24, height=2).pack(pady=(30, 12))
    tk.Button(root, text="オーバーレイを開く", command=lambda: webbrowser.open("http://127.0.0.1:8776/overlay.html"),
              bg="#2a2f3b", fg="white", relief="flat", font=("Yu Gothic UI", 11), width=24).pack()
    tk.Label(root, text="この画面を閉じるとMinecraft連携も終了します。", fg="#8991a3", bg="#11141b",
             font=("Yu Gothic UI", 9)).pack(pady=22)
    def close():
        httpd.shutdown(); root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()

