"""
streamlink pipe 管理
通过 streamlink 以 pipe 模式拉取 YouTube 直播流
所有网络请求在同一进程内完成，确保代理出口 IP 一致
支持通过 cookies.txt 文件传递浏览器登录态

使用 subprocess.Popen 管理进程，stdout 可直接传给 FFmpeg 作为 stdin
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger("stream_fetcher")


class StreamFetcher:
    """通过 streamlink pipe 模式拉取直播流"""

    def __init__(self, config: dict, cookies_file: str = ""):
        self.youtube_url = config["youtube_url"]
        self.proxy = config["proxy"]
        self.quality = config.get("quality", "best")
        self.cookies_file = cookies_file
        self._process: Optional[subprocess.Popen] = None

    @staticmethod
    def check_available() -> bool:
        """检查 streamlink 是否可用"""
        return shutil.which("streamlink") is not None

    def start(self):
        """
        启动 streamlink 进程
        返回 Popen 对象，其 stdout 可直接传给 FFmpeg 的 stdin
        """
        if self._process and self._process.poll() is None:
            logger.warning("streamlink 进程已在运行")
            return self._process

        cmd = self._build_command()
        logger.info(f"启动 streamlink: {' '.join(cmd)}")

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # 无缓冲，数据立即传递
        )

        # 在后台线程中读取 stderr，避免缓冲区满阻塞
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True
        )
        self._stderr_thread.start()

        # 等待 streamlink 解析流并开始输出数据
        self._wait_for_output(timeout=15)

        logger.info("streamlink 进程已启动")
        return self._process

    def _wait_for_output(self, timeout: int = 15):
        """等待 streamlink 开始输出数据或退出"""
        start = time.time()
        while time.time() - start < timeout:
            # 进程已退出
            if self._process.poll() is not None:
                stderr_text = self._process.stderr.read().decode(errors="replace")[:500]
                raise RuntimeError(
                    f"streamlink 启动失败 (exit code {self._process.returncode}): "
                    f"{stderr_text}"
                )
            # 检查 stdout 是否有数据
            # 使用 peek 非阻塞检查
            import select
            if hasattr(select, "select"):
                ready, _, _ = select.select([self._process.stdout], [], [], 0.5)
                if ready:
                    return
            else:
                # Windows 没有 select 对 pipe 的支持，简单 sleep
                time.sleep(0.5)
                if self._process.stdout and self._process.stdout.readable():
                    return

        # 超时但进程还在运行，可能是正常的（直播还在加载）
        if self._process.poll() is None:
            logger.warning(f"streamlink 在 {timeout}s 内未开始输出数据，但进程仍在运行")

    def _drain_stderr(self):
        """后台线程：持续读取 stderr"""
        try:
            for line in iter(self._process.stderr.readline, b""):
                text = line.decode(errors="replace").strip()
                if text:
                    logger.debug(f"[streamlink] {text}")
        except Exception:
            pass

    def _build_command(self) -> list:
        """构建 streamlink 命令行"""
        cmd = [
            "streamlink",
            "--http-proxy", self.proxy,
            "--force",
            "--retry-streams", "5",
            "--retry-open", "3",
            "--hls-live-restart",
            "--stream-segment-timeout", "30",
            "--stream-timeout", "60",
        ]

        # 添加 cookies 文件
        if self.cookies_file and os.path.exists(self.cookies_file):
            cmd.extend(["--http-cookies-file", os.path.abspath(self.cookies_file)])
            logger.info(f"使用 cookies 文件: {self.cookies_file}")
        else:
            logger.warning("未找到 cookies 文件，可能无法访问需要登录的直播")

        cmd.extend([self.youtube_url, self.quality, "-O"])  # -O = pipe 模式
        return cmd

    @property
    def is_running(self) -> bool:
        """进程是否在运行"""
        return self._process is not None and self._process.poll() is None

    @property
    def returncode(self) -> Optional[int]:
        """进程退出码"""
        return self._process.returncode if self._process else None

    def stop(self):
        """停止 streamlink 进程"""
        if self._process and self._process.poll() is None:
            logger.info("正在停止 streamlink 进程...")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("streamlink 未响应 terminate，使用 kill")
                self._process.kill()
                self._process.wait()
            logger.info("streamlink 进程已停止")
        self._process = None
