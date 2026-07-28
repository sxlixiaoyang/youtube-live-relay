"""
简易 RTMP 播放器 - 无任何控件、无边框，仅视频画面
用法: python player.py [rtmp地址]
F11: 全屏 / 退出全屏
ESC: 退出
"""
import sys
import tkinter as tk
from tkinter import ttk
import vlc


def show_input_dialog():
    """弹出输入地址的对话框，返回用户输入的 RTMP 地址"""
    result = {"url": None}

    root = tk.Tk()
    root.title("RTMP 播放器")
    root.configure(bg="#1e1e1e")
    root.resizable(False, False)

    # 居中
    w, h = 480, 200
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # 标题
    tk.Label(root, text="🎬 RTMP 播放器", font=("Microsoft YaHei", 16, "bold"),
             fg="#ffffff", bg="#1e1e1e").pack(pady=(25, 10))

    # 输入框
    frame = tk.Frame(root, bg="#1e1e1e")
    frame.pack(padx=30, fill=tk.X)

    entry = tk.Entry(frame, font=("Consolas", 12), bg="#2d2d2d", fg="#ffffff",
                     insertbackground="#ffffff", relief=tk.FLAT, bd=8)
    entry.pack(fill=tk.X, ipady=6)
    entry.insert(0, "rtmp://")
    entry.select_range(0, tk.END)
    entry.focus_set()

    # 按钮
    btn_frame = tk.Frame(root, bg="#1e1e1e")
    btn_frame.pack(pady=(15, 0))

    def on_play():
        url = entry.get().strip()
        if url and url != "rtmp://":
            result["url"] = url
            root.destroy()

    def on_cancel():
        root.destroy()

    play_btn = tk.Button(btn_frame, text="▶ 播放", font=("Microsoft YaHei", 11),
                         bg="#0078d4", fg="#ffffff", activebackground="#005a9e",
                         activeforeground="#ffffff", relief=tk.FLAT, padx=25, pady=4,
                         command=on_play, cursor="hand2")
    play_btn.pack(side=tk.LEFT, padx=8)

    cancel_btn = tk.Button(btn_frame, text="取消", font=("Microsoft YaHei", 11),
                           bg="#3d3d3d", fg="#cccccc", activebackground="#555555",
                           activeforeground="#ffffff", relief=tk.FLAT, padx=25, pady=4,
                           command=on_cancel, cursor="hand2")
    cancel_btn.pack(side=tk.LEFT, padx=8)

    # 回车键播放
    root.bind("<Return>", lambda e: on_play())
    root.bind("<Escape>", lambda e: on_cancel())

    root.mainloop()
    return result["url"]


def play(rtmp_url: str):
    root = tk.Tk()
    root.title("")
    root.configure(bg="black")

    # 无边框、无标题栏
    root.overrideredirect(True)

    # 默认窗口大小，居中
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w, h = 960, 540
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # VLC 播放器
    instance = vlc.Instance("--no-video-title-show --network-caching=300")
    player = instance.media_player_new()
    media = instance.media_new(rtmp_url)
    media.add_option(":network-caching=300")
    player.set_media(media)

    # 画布
    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    root.update_idletasks()

    hwnd = canvas.winfo_id()
    if sys.platform == "win32":
        player.set_hwnd(hwnd)
    elif sys.platform == "darwin":
        player.set_nsobject(hwnd)
    else:
        player.set_xwindow(hwnd)

    player.play()

    is_fullscreen = False

    # F11 切换全屏
    def toggle_fullscreen(event=None):
        nonlocal is_fullscreen
        is_fullscreen = not is_fullscreen
        if is_fullscreen:
            root.attributes("-fullscreen", True)
        else:
            root.attributes("-fullscreen", False)
            root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    root.bind("<F11>", toggle_fullscreen)

    # ESC 退出
    root.bind("<Escape>", lambda e: on_close())

    def on_close():
        player.stop()
        player.release()
        instance.release()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    # 优先使用命令行参数，否则弹出输入对话框
    if len(sys.argv) >= 2:
        url = sys.argv[1]
    else:
        url = show_input_dialog()

    if not url:
        sys.exit(0)

    play(url)
