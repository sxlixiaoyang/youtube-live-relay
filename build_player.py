#!/usr/bin/env python3
"""
RTMP 播放器 - 打包脚本
将 player.py 打包为独立可执行程序

用法:
  python build_player.py              # 打包当前平台
  python build_player.py --clean      # 清理后重新打包
  python build_player.py --onefile    # 单文件模式
"""

import os
import shutil
import subprocess
import sys
import platform

# 确保控制台输出 UTF-8（Windows cp1252 无法处理中文）
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr.reconfigure(encoding='utf-8')

# ---- 配置 ----
APP_NAME = "rtmp-player"
MAIN_SCRIPT = "player.py"

# PyInstaller 隐式导入
HIDDEN_IMPORTS = [
    "vlc",
]

# 排除的大型模块（减小体积）
EXCLUDES = [
    "unittest",
    "test",
    "tests",
    "pip",
    "flask",
    "waitress",
    "yaml",
    "streamlink",
]


def get_pyinstaller_args(mode: str = "onedir") -> list:
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm"]

    if mode == "onefile":
        args.append("--onefile")
    else:
        args.append("--onedir")

    args.extend(["--name", APP_NAME])

    # 无控制台窗口（GUI 程序）
    args.append("--noconsole")

    for mod in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", mod])

    for mod in EXCLUDES:
        args.extend(["--exclude-module", mod])

    # 图标
    if platform.system() == "Windows" and os.path.exists("icon.ico"):
        args.extend(["--icon", "icon.ico"])

    args.append(MAIN_SCRIPT)
    return args


def main():
    import argparse
    parser = argparse.ArgumentParser(description="打包 RTMP 播放器")
    parser.add_argument("--clean", action="store_true", help="清理后重新打包")
    parser.add_argument("--onefile", action="store_true", help="单文件模式")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 50)
    print("  RTMP 播放器 - 打包工具")
    print("=" * 50)
    print(f"  平台: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version}")
    print(f"  模式: {'单文件' if args.onefile else '目录'}")
    print()

    # 清理
    if args.clean:
        for d in ["build", f"{APP_NAME}.spec"]:
            if os.path.exists(d):
                if os.path.isdir(d):
                    shutil.rmtree(d)
                else:
                    os.remove(d)
                print(f"  清理: {d}")
        dist_player = os.path.join("dist", APP_NAME)
        if os.path.exists(dist_player):
            shutil.rmtree(dist_player)
            print(f"  清理: {dist_player}")

    # 检查 PyInstaller
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("正在安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    # 执行打包
    mode = "onefile" if args.onefile else "onedir"
    cmd = get_pyinstaller_args(mode)

    print(f"\n执行 PyInstaller...")
    print(f"命令: {' '.join(cmd)}\n")

    subprocess.check_call(cmd)

    # 完成
    if mode == "onefile":
        dist_dir = "dist"
    else:
        dist_dir = os.path.join("dist", APP_NAME)

    print(f"\n{'='*50}")
    print("  打包完成！")
    print(f"{'='*50}")
    print(f"  输出目录: {os.path.abspath(dist_dir)}")

    if platform.system() == "Windows":
        ext = ".exe"
    else:
        ext = ""
    exe_path = os.path.join(dist_dir, APP_NAME + ext)
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"  可执行文件: {exe_path} ({size_mb:.1f} MB)")

    print()
    print("  注意: 运行需要系统已安装 VLC 播放器")
    print()


if __name__ == "__main__":
    main()
