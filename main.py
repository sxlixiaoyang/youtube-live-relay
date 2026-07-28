"""
YouTube 直播转播 - 主入口
通过 streamlink pipe + FFmpeg 将 YouTube 直播流转播到本地 RTMP 服务器
支持通过 Chrome 扩展传递浏览器登录态 cookies
"""

import asyncio
import logging
import os
import signal
import sys
import yaml

from cookie_server import CookieServer
from watchdog import Watchdog
from web_ui import WebUI

logger = logging.getLogger("main")


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        print("请复制 config.yaml 并修改其中的配置项")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 验证必要配置项
    required_keys = ["proxy", "youtube_url"]
    for key in required_keys:
        if key not in config or not config[key]:
            print(f"配置缺少必要项: {key}")
            sys.exit(1)

    # 设置默认值
    config.setdefault("quality", "best")
    config.setdefault("rtmp", {})
    config["rtmp"].setdefault("host", "localhost")
    config["rtmp"].setdefault("port", 1935)
    config["rtmp"].setdefault("app", "live")
    config["rtmp"].setdefault("key", "youtube")
    config.setdefault("reconnect", {})
    config["reconnect"].setdefault("max_retries", 0)
    config["reconnect"].setdefault("initial_delay", 3)
    config["reconnect"].setdefault("max_delay", 60)
    config["reconnect"].setdefault("backoff_factor", 2)
    config.setdefault("ffmpeg", {})
    config["ffmpeg"].setdefault("loglevel", "warning")
    config["ffmpeg"].setdefault("video_codec", "copy")
    config["ffmpeg"].setdefault("audio_codec", "copy")
    config.setdefault("logging", {})
    config.setdefault("cookie_server", {})
    config["cookie_server"].setdefault("host", "localhost")
    config["cookie_server"].setdefault("port", 8080)
    config["cookie_server"].setdefault("cookies_file", "cookies.txt")
    config.setdefault("web_ui", {})
    config["web_ui"].setdefault("host", "localhost")
    config["web_ui"].setdefault("port", 5000)
    config.setdefault("enable_ui", True)

    return config


def setup_logging(config: dict):
    """配置日志"""
    log_cfg = config.get("logging", {})
    level_name = log_cfg.get("level", "INFO")
    log_file = log_cfg.get("file", "")

    level = getattr(logging, level_name.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def check_dependencies(config: dict):
    """检查依赖是否安装"""
    from stream_fetcher import StreamFetcher
    from ffmpeg_relay import FfmpegRelay

    missing = []
    if not StreamFetcher.check_available():
        missing.append("streamlink")
    if not FfmpegRelay.check_available(config):
        missing.append("ffmpeg")

    if missing:
        print(f"缺少必要依赖: {', '.join(missing)}")
        print()
        if "streamlink" in missing:
            print("安装 streamlink:")
            print("  pip install streamlink")
        if "ffmpeg" in missing:
            print("安装 ffmpeg:")
            print("  1. 在 config.yaml 中配置 ffmpeg.path 指向本地 ffmpeg.exe")
            print("  2. 或安装到系统: winget install ffmpeg")
        sys.exit(1)


def print_banner(config: dict, cookie_server: CookieServer):
    """打印启动信息"""
    rtmp = config["rtmp"]
    rtmp_url = f"rtmp://{rtmp['host']}:{rtmp['port']}/{rtmp['app']}/{rtmp['key']}"
    cs_cfg = config["cookie_server"]
    cookie_url = f"http://{cs_cfg['host']}:{cs_cfg['port']}/api/cookies"

    print("=" * 60)
    print("  YouTube 直播转播")
    print("=" * 60)
    print(f"  直播源:     {config['youtube_url']}")
    print(f"  代理:       {config['proxy']}")
    print(f"  画质:       {config['quality']}")
    print(f"  推流目标:   {rtmp_url}")
    print("-" * 60)
    print(f"  Cookie服务: {cookie_url}")
    print(f"  Cookies数:  {cookie_server.cookie_manager.cookie_count}")
    print("=" * 60)
    print()
    print("  使用步骤:")
    print("  1. 在 Chrome 中安装扩展: chrome-extension/")
    print("  2. 打开 YouTube 页面，扩展会自动发送 Cookies")
    print("  3. OBS 添加「媒体源」→ 输入上述推流目标地址")
    print("=" * 60)
    print()


async def run_mediamtx(config: dict) -> asyncio.subprocess.Process | None:
    """启动 mediamtx RTMP 服务器"""
    mediamtx_cfg = config.get("mediamtx", {})
    exe_path = mediamtx_cfg.get("path", "./mediamtx/mediamtx.exe")
    config_path = mediamtx_cfg.get("config", "")

    if not os.path.exists(exe_path):
        logger.warning(f"mediamtx 不存在: {exe_path}")
        logger.warning("RTMP 服务器未启动，请确保有其他 RTMP 服务在运行")
        logger.warning("或下载 mediamtx: https://github.com/bluenviron/mediamtx/releases")
        return None

    cmd = [exe_path]
    if config_path and os.path.exists(config_path):
        cmd.extend([config_path])

    logger.info(f"启动 mediamtx: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 等待 mediamtx 启动
    await asyncio.sleep(2)
    if process.returncode is not None:
        logger.error("mediamtx 启动失败")
        return None

    logger.info("mediamtx RTMP 服务器已启动")
    return process


async def main():
    config_path = os.environ.get("RELAY_CONFIG", "config.yaml")
    config = load_config(config_path)
    setup_logging(config)
    check_dependencies(config)

    # 启动 Cookie 接收服务器
    cs_cfg = config["cookie_server"]
    cookie_server = CookieServer(
        host=cs_cfg["host"],
        port=cs_cfg["port"],
        cookies_file=cs_cfg["cookies_file"],
    )
    cookie_server.start()

    print_banner(config, cookie_server)

    # 启动 Web UI
    web_ui = None
    restart_event = asyncio.Event()
    if config.get("enable_ui", True):
        ui_cfg = config.get("web_ui", {})
        web_ui = WebUI(
            config=config,
            host=ui_cfg.get("host", "localhost"),
            port=ui_cfg.get("port", 5000),
        )
        web_ui.cookie_server = cookie_server
        web_ui.start(loop=asyncio.get_event_loop(), restart_event=restart_event)
        print(f"  Web UI:     http://{ui_cfg.get('host', 'localhost')}:{ui_cfg.get('port', 5000)}")
        print()

    # 启动 mediamtx
    mediamtx_process = await run_mediamtx(config)

    # 创建守护进程，传入 cookies 文件路径
    cookies_file = cs_cfg["cookies_file"]
    watchdog = Watchdog(config, cookies_file=cookies_file)

    # 关联 Web UI 与 Watchdog
    if web_ui:
        web_ui.watchdog = watchdog

    # 信号处理
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("收到停止信号")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: signal_handler())

    # 主循环：支持 Web UI 启动/停止/重启
    watchdog_task = None
    while not stop_event.is_set():
        # 启动 watchdog
        watchdog_task = asyncio.create_task(watchdog.start())

        # 等待 watchdog 结束或程序停止信号
        stop_waiter = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {watchdog_task, stop_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        # 取消未完成的 waiter
        stop_waiter.cancel()

        # 如果是程序停止信号，退出
        if stop_event.is_set():
            await watchdog.stop()
            try:
                await asyncio.wait_for(watchdog_task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("watchdog 未正常退出")
            watchdog_task = None
            break

        # watchdog 停止了（被 Web UI 停止或异常），等待重启信号或程序停止
        logger.info("转播已停止，等待重启...")

        # 等待重启信号或停止信号
        restart_waiter = asyncio.create_task(restart_event.wait())
        stop_waiter2 = asyncio.create_task(stop_event.wait())
        done2, pending2 = await asyncio.wait(
            {restart_waiter, stop_waiter2},
            return_when=asyncio.FIRST_COMPLETED,
        )
        restart_waiter.cancel()
        stop_waiter2.cancel()

        if stop_event.is_set():
            break

        # 收到重启信号
        restart_event.clear()
        watchdog.reset()
        logger.info("正在重启转播...")

    # 最终清理
    if watchdog_task and not watchdog_task.done():
        await watchdog.stop()
        try:
            await asyncio.wait_for(watchdog_task, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("watchdog 未正常退出")

    cookie_server.stop()
    if mediamtx_process and mediamtx_process.returncode is None:
        mediamtx_process.terminate()
        await mediamtx_process.wait()

    logger.info("程序已退出")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已退出")
