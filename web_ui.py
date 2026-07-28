"""
YouTube 直播转播 - Web UI
基于 Flask 的 Web 管理界面，提供状态监控、日志查看、配置编辑等功能
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
import traceback
from typing import Optional

from flask import Flask, render_template, request, jsonify

logger = logging.getLogger("web_ui")


def _get_resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，兼容 PyInstaller 打包模式"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式，资源解压到 sys._MEIPASS 目录
        base_path = sys._MEIPASS
    else:
        # 开发模式，使用脚本所在目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class WebUI:
    """Web UI 服务器"""

    def __init__(self, config: dict, host: str = "localhost", port: int = 5000):
        self.config = config
        self.host = host
        self.port = port
        self._app = Flask(__name__, template_folder=_get_resource_path("templates"))
        self._app.config["JSON_AS_ASCII"] = False
        self._thread: Optional[threading.Thread] = None
        self._server = None

        # 引用外部组件（由 main.py 设置）
        self.watchdog = None
        self.cookie_server = None
        self.mediamtx_process = None
        self.start_time = time.time()

        # 控制事件（由 main.py 设置）
        self._restart_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 日志缓冲区
        self._log_buffer: list[dict] = []
        self._log_max = 500
        self._setup_log_handler()

        # 注册路由
        self._register_routes()

    def _setup_log_handler(self):
        """设置日志处理器，捕获日志到缓冲区"""
        handler = _LogBufferHandler(self._log_buffer, self._log_max)
        handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(handler)

    def _register_routes(self):
        """注册所有路由"""

        @self._app.route("/")
        def index():
            return render_template("index.html")

        # ---- 状态 API ----
        @self._app.route("/api/status")
        def api_status():
            wd = self.watchdog
            cs = self.cookie_server
            rtmp = self.config.get("rtmp", {})
            rtmp_url = f"rtmp://{rtmp.get('host','localhost')}:{rtmp.get('port',1935)}/{rtmp.get('app','live')}/{rtmp.get('key','youtube')}"

            fetcher_alive = wd.fetcher.is_running if wd and wd.fetcher else False
            relay_alive = wd.relay.is_running if wd and wd.relay else False

            uptime = time.time() - self.start_time if self.start_time else 0

            return jsonify({
                "success": True,
                "running": wd.is_running if wd else False,
                "uptime": round(uptime, 1),
                "pipeline": {
                    "streamlink": {
                        "alive": fetcher_alive,
                        "exit_code": wd.fetcher.returncode if wd and wd.fetcher and not fetcher_alive else None,
                    },
                    "ffmpeg": {
                        "alive": relay_alive,
                        "exit_code": wd.relay.returncode if wd and wd.relay and not relay_alive else None,
                    },
                },
                "reconnect": {
                    "retry_count": wd.retry_count if wd else 0,
                    "max_retries": self.config.get("reconnect", {}).get("max_retries", 0),
                },
                "cookies": {
                    "count": cs.cookie_manager.cookie_count if cs else 0,
                    "last_update": cs.cookie_manager.last_update if cs else 0,
                },
                "rtmp_url": rtmp_url,
                "youtube_url": self.config.get("youtube_url", ""),
                "proxy": self.config.get("proxy", ""),
                "quality": self.config.get("quality", "best"),
            })

        # ---- 日志 API ----
        @self._app.route("/api/logs")
        def api_logs():
            offset = request.args.get("offset", 0, type=int)
            limit = request.args.get("limit", 100, type=int)
            logs = self._log_buffer[offset:offset + limit]
            return jsonify({
                "success": True,
                "logs": logs,
                "total": len(self._log_buffer),
            })

        # ---- 配置 API ----
        @self._app.route("/api/config")
        def api_config():
            return jsonify({
                "success": True,
                "config": self.config,
            })

        @self._app.route("/api/config", methods=["POST"])
        def api_config_update():
            try:
                data = request.get_json(force=True)
                if not data:
                    return jsonify({"success": False, "message": "无数据"}), 400

                # 允许更新的配置项
                updatable = ["proxy", "youtube_url", "quality"]
                updated = []
                for key in updatable:
                    if key in data:
                        self.config[key] = data[key]
                        updated.append(key)

                # RTMP 子项
                if "rtmp" in data:
                    for k, v in data["rtmp"].items():
                        self.config.setdefault("rtmp", {})[k] = v
                        updated.append(f"rtmp.{k}")

                # FFmpeg 子项
                if "ffmpeg" in data:
                    for k, v in data["ffmpeg"].items():
                        self.config.setdefault("ffmpeg", {})[k] = v
                        updated.append(f"ffmpeg.{k}")

                # 保存到文件
                config_path = os.environ.get("RELAY_CONFIG", "config.yaml")
                try:
                    import yaml
                    with open(config_path, "w", encoding="utf-8") as f:
                        yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                except Exception as e:
                    logger.warning(f"保存配置文件失败: {e}")

                return jsonify({
                    "success": True,
                    "message": f"已更新: {', '.join(updated)}",
                    "updated": updated,
                })
            except Exception as e:
                return jsonify({"success": False, "message": str(e)}), 500

        # ---- 控制 API ----
        @self._app.route("/api/start", methods=["POST"])
        def api_start():
            wd = self.watchdog
            if wd and wd.is_running:
                return jsonify({"success": False, "message": "已在运行中"})
            if self._restart_event and self._loop:
                # 在主线程事件循环中设置重启事件
                self._loop.call_soon_threadsafe(self._restart_event.set)
                return jsonify({"success": True, "message": "正在启动..."})
            return jsonify({"success": False, "message": "无法启动"})

        @self._app.route("/api/stop", methods=["POST"])
        def api_stop():
            wd = self.watchdog
            if wd and wd.is_running:
                asyncio.run_coroutine_threadsafe(wd.stop(), self._loop)
                return jsonify({"success": True, "message": "正在停止..."})
            return jsonify({"success": False, "message": "未在运行"})

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None,
              restart_event: Optional[asyncio.Event] = None):
        """启动 Web UI 服务器"""
        self._loop = loop
        self._restart_event = restart_event
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info(f"Web UI 已启动: http://{self.host}:{self.port}")

    def _run_server(self):
        """在后台线程中运行 Flask"""
        try:
            from waitress import serve as waitress_serve
            waitress_serve(self._app, host=self.host, port=self.port, _quiet=True)
        except ImportError:
            # waitress 不可用时使用 Flask 内置服务器
            self._app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

    def stop(self):
        """停止 Web UI"""
        # Flask 在 daemon 线程中，主线程退出时自动结束
        logger.info("Web UI 已停止")


class _LogBufferHandler(logging.Handler):
    """日志缓冲区处理器"""

    def __init__(self, buffer: list, max_size: int = 500):
        super().__init__()
        self._buffer = buffer
        self._max_size = max_size

    def emit(self, record: logging.LogRecord):
        try:
            entry = {
                "time": self.format_time(record),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format_message(record),
            }
            self._buffer.append(entry)
            # 限制缓冲区大小
            if len(self._buffer) > self._max_size:
                del self._buffer[:len(self._buffer) - self._max_size]
        except Exception:
            pass

    @staticmethod
    def format_time(record: logging.LogRecord) -> str:
        return time.strftime("%H:%M:%S", time.localtime(record.created))

    @staticmethod
    def format_message(record: logging.LogRecord) -> str:
        try:
            return record.getMessage()
        except Exception:
            return str(record.msg)
