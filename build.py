#!/usr/bin/env python3
"""
YouTube 直播转播 - 打包脚本
使用 PyInstaller 将项目打包为可执行程序

用法:
  python build.py              # 打包当前平台
  python build.py --clean      # 清理后重新打包
  python build.py --onefile    # 单文件模式（体积更大、启动更慢）
"""

import os
import shutil
import subprocess
import sys
import platform

# ---- 配置 ----
APP_NAME = "youtube-relay"
MAIN_SCRIPT = "main.py"

# 需要打包进可执行文件的数据文件（PyInstaller --add-data）
BUNDLE_DATA = [
    ("templates", "templates"),
]

# 需要复制到 dist 目录的外部文件（不打包进可执行文件）
COPY_FILES = [
    "config.yaml",
    "cookies.txt",
    "README.md",
]

# 需要复制到 dist 目录的整个文件夹
COPY_DIRS = [
    "chrome-extension",
    "mediamtx",
]

# PyInstaller 隐式导入（无法自动检测的模块）
HIDDEN_IMPORTS = [
    "flask",
    "waitress",
    "yaml",
    "streamlink",
    "streamlink.plugins",
    "streamlink.plugins.youtube",
    "streamlink.stream",
    "streamlink.session",
    # pkg_resources 运行时钩的依赖
    "pkg_resources",
    "pkg_resources.py2_warn",
    "jaraco",
    "jaraco.text",
    "jaraco.functools",
    "jaraco.context",
    "more_itertools",
]

# 排除的大型模块（减小体积）
EXCLUDES = [
    "tkinter",
    "unittest",
    "test",
    "tests",
]


def get_pyinstaller_args(mode: str = "onedir") -> list:
    """构建 PyInstaller 命令行参数"""
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm"]

    if mode == "onefile":
        args.append("--onefile")
    else:
        args.append("--onedir")

    # 应用名
    args.extend(["--name", APP_NAME])

    # 数据文件
    for src, dst in BUNDLE_DATA:
        if os.path.exists(src):
            sep = ";" if platform.system() == "Windows" else ":"
            args.extend(["--add-data", f"{src}{sep}{dst}"])

    # 隐式导入
    for mod in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", mod])

    # 排除模块
    for mod in EXCLUDES:
        args.extend(["--exclude-module", mod])

    # 控制台模式（需要看到日志输出）
    args.append("--console")

    # 图标（如果存在）
    if platform.system() == "Windows" and os.path.exists("icon.ico"):
        args.extend(["--icon", "icon.ico"])
    elif platform.system() != "Windows" and os.path.exists("icon.png"):
        args.extend(["--icon", "icon.png"])

    # 主脚本
    args.append(MAIN_SCRIPT)

    return args


def copy_extra_files(dist_dir: str):
    """复制外部文件到 dist 目录"""
    print(f"\n{'='*50}")
    print("复制外部文件...")
    print(f"{'='*50}")

    for f in COPY_FILES:
        src = os.path.join(os.path.dirname(__file__), f)
        dst = os.path.join(dist_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  复制: {f}")
        else:
            print(f"  跳过（不存在）: {f}")

    for d in COPY_DIRS:
        src = os.path.join(os.path.dirname(__file__), d)
        dst = os.path.join(dist_dir, d)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  复制目录: {d}/")
        else:
            print(f"  跳过（不存在）: {d}/")


def create_run_script(dist_dir: str):
    """创建启动脚本"""
    system = platform.system()

    if system == "Windows":
        script_content = """@echo off
chcp 65001 >nul
title YouTube 直播转播
echo ========================================
echo   YouTube 直播转播
echo ========================================
echo.
youtube-relay.exe
pause
"""
        script_path = os.path.join(dist_dir, "启动转播.bat")
    else:
        script_content = """#!/bin/bash
cd "$(dirname "$0")"
echo "========================================"
echo "  YouTube 直播转播"
echo "========================================"
echo
./youtube-relay
"""
        script_path = os.path.join(dist_dir, "启动转播.sh")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    if system != "Windows":
        os.chmod(script_path, 0o755)

    print(f"  创建启动脚本: {os.path.basename(script_path)}")


def clean():
    """清理构建产物"""
    dirs_to_clean = ["build", "dist", f"{APP_NAME}.spec"]
    for d in dirs_to_clean:
        if os.path.exists(d):
            if os.path.isdir(d):
                shutil.rmtree(d)
            else:
                os.remove(d)
            print(f"  清理: {d}")


def check_pyinstaller():
    """检查并安装 PyInstaller"""
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])
        print("PyInstaller 安装完成")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="打包 YouTube 直播转播")
    parser.add_argument("--clean", action="store_true", help="清理后重新打包")
    parser.add_argument("--onefile", action="store_true", help="单文件模式（默认为目录模式）")
    args = parser.parse_args()

    # 切换到脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 60)
    print("  YouTube 直播转播 - 打包工具")
    print("=" * 60)
    print(f"  平台: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version}")
    print(f"  模式: {'单文件' if args.onefile else '目录'}")
    print()

    # 清理
    if args.clean:
        print("清理构建产物...")
        clean()
        print()

    # 检查依赖
    check_pyinstaller()

    # 执行打包
    mode = "onefile" if args.onefile else "onedir"
    cmd = get_pyinstaller_args(mode)

    print(f"\n{'='*50}")
    print("执行 PyInstaller...")
    print(f"{'='*50}")
    print(f"命令: {' '.join(cmd)}")
    print()

    subprocess.check_call(cmd)

    # 复制外部文件
    if mode == "onefile":
        dist_dir = "dist"
    else:
        dist_dir = os.path.join("dist", APP_NAME)

    copy_extra_files(dist_dir)
    create_run_script(dist_dir)

    # 完成
    print(f"\n{'='*60}")
    print("  打包完成！")
    print(f"{'='*60}")
    print(f"  输出目录: {os.path.abspath(dist_dir)}")

    if mode == "onefile":
        ext = ".exe" if platform.system() == "Windows" else ""
        print(f"  可执行文件: {os.path.abspath(os.path.join(dist_dir, APP_NAME + ext))}")
    else:
        print(f"  可执行文件: {os.path.abspath(dist_dir)}/")

    print()
    print("  使用前请确保:")
    print("  1. 已安装 streamlink (pip install streamlink 或系统包管理器)")
    print("  2. 已安装 ffmpeg    (系统包管理器或手动下载)")
    print("  3. 已配置 config.yaml 中的代理和直播地址")
    print()

    # 打包信息
    if platform.system() == "Linux":
        print("  Linux 部署提示:")
        print("  - streamlink: sudo apt install streamlink 或 pip install streamlink")
        print("  - ffmpeg:     sudo apt install ffmpeg")
        print("  - 需要赋予执行权限: chmod +x youtube-relay")
        print()


if __name__ == "__main__":
    main()
