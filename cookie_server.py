"""
Cookies 接收服务器
接收 Chrome 扩展发送的 YouTube Cookies，保存为 Netscape cookies.txt 格式
供 streamlink 的 --http-cookies-file 参数使用
"""

import json
import logging
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock
from typing import Optional

logger = logging.getLogger("cookie_server")

# Netscape cookies.txt 格式头
COOKIES_TXT_HEADER = """# Netscape HTTP Cookie File
# https://curl.se/docs/http-cookies.html
# This file was generated automatically by YouTube Relay

"""


class CookieManager:
    """管理 cookies 的存储和文件生成"""

    def __init__(self, cookies_file: str = "cookies.txt"):
        self.cookies_file = cookies_file
        self._cookies: list[dict] = []
        self._lock = Lock()
        self._last_update: float = 0

    @property
    def cookies(self) -> list[dict]:
        with self._lock:
            return self._cookies.copy()

    @property
    def cookie_count(self) -> int:
        with self._lock:
            return len(self._cookies)

    @property
    def last_update(self) -> float:
        return self._last_update

    def update_cookies(self, cookies: list[dict]) -> int:
        """
        更新 cookies 并写入文件
        返回写入的 cookie 数量
        """
        # 只保留 youtube.com 域名的 cookies
        yt_cookies = [
            c for c in cookies
            if ".youtube.com" in c.get("domain", "")
        ]

        if not yt_cookies:
            logger.warning("收到的 cookies 中没有 YouTube 域名的")
            return 0

        with self._lock:
            self._cookies = yt_cookies
            self._last_update = time.time()

        self._write_cookies_file()

        logger.info(f"已更新 {len(yt_cookies)} 个 YouTube cookies")
        return len(yt_cookies)

    def _write_cookies_file(self):
        """将 cookies 写入 Netscape 格式文件"""
        with self._lock:
            cookies = self._cookies.copy()

        try:
            with open(self.cookies_file, "w", encoding="utf-8") as f:
                f.write(COOKIES_TXT_HEADER)
                for c in cookies:
                    # Netscape 格式:
                    # domain \t include_subdomains \t path \t secure \t expiration \t name \t value
                    domain = c.get("domain", ".youtube.com")
                    include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
                    path = c.get("path", "/")
                    secure = "TRUE" if c.get("secure", False) else "FALSE"
                    expiration = str(int(c.get("expirationDate", 0)))
                    name = c.get("name", "")
                    value = c.get("value", "")

                    f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")

            logger.debug(f"Cookies 文件已写入: {self.cookies_file}")
        except Exception as e:
            logger.error(f"写入 cookies 文件失败: {e}")

    def get_cookies_file_path(self) -> Optional[str]:
        """获取 cookies 文件路径，如果文件存在的话"""
        if os.path.exists(self.cookies_file):
            return self.cookies_file
        return None


class CookieHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    cookie_manager: CookieManager  # 类变量，由外部设置

    def do_GET(self):
        """GET 请求 - 返回 cookies 状态"""
        if self.path == "/api/cookies":
            self._send_json(200, {
                "success": True,
                "cookie_count": self.cookie_manager.cookie_count,
                "last_update": self.cookie_manager.last_update,
            })
        else:
            self._send_json(404, {"success": False, "message": "Not found"})

    def do_POST(self):
        """POST 请求 - 接收 cookies"""
        if self.path == "/api/cookies":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))

                cookies = data.get("cookies", [])
                if not cookies:
                    self._send_json(400, {"success": False, "message": "No cookies provided"})
                    return

                count = self.cookie_manager.update_cookies(cookies)
                self._send_json(200, {
                    "success": True,
                    "message": f"Updated {count} cookies",
                    "cookie_count": count,
                })
            except json.JSONDecodeError:
                self._send_json(400, {"success": False, "message": "Invalid JSON"})
            except Exception as e:
                self._send_json(500, {"success": False, "message": str(e)})
        else:
            self._send_json(404, {"success": False, "message": "Not found"})

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, code: int, data: dict):
        self.send_response(code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _set_cors_headers(self):
        """设置 CORS 头，允许浏览器扩展访问"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        """覆盖默认日志，使用 Python logging"""
        logger.debug(f"HTTP {args[0]}")


class CookieServer:
    """Cookies 接收服务器"""

    def __init__(self, host: str = "localhost", port: int = 8080,
                 cookies_file: str = "cookies.txt"):
        self.host = host
        self.port = port
        self.cookie_manager = CookieManager(cookies_file)
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[Thread] = None

    def start(self):
        """启动 HTTP 服务器（在后台线程中）"""
        CookieHandler.cookie_manager = self.cookie_manager

        self._server = HTTPServer((self.host, self.port), CookieHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(f"Cookies 接收服务器已启动: http://{self.host}:{self.port}")
        logger.info(f"  Chrome 扩展发送地址: http://{self.host}:{self.port}/api/cookies")
        logger.info(f"  Cookies 文件: {os.path.abspath(self.cookie_manager.cookies_file)}")

    def stop(self):
        """停止 HTTP 服务器"""
        if self._server:
            self._server.shutdown()
            logger.info("Cookies 接收服务器已停止")

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def has_cookies(self) -> bool:
        return self.cookie_manager.cookie_count > 0
