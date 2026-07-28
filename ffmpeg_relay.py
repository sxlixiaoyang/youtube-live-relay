"""
FFmpeg 推流管理
从 stdin (pipe) 读取流数据，推流到本地 RTMP 服务器
FFmpeg 不需要代理，所有网络请求由 streamlink 完成

使用 subprocess.Popen 管理进程，stdin 直接接收 streamlink 的 stdout
"""

import logging
import os
import shutil
import subprocess
import threading
from typing import Optional

logger = logging.getLogger("ffmpeg_relay")


class FfmpegRelay:
    """FFmpeg 推流：从 pipe 读取，推送到 RTMP"""

    def __init__(self, config: dict):
        rtmp_cfg = config["rtmp"]
        ffmpeg_cfg = config.get("ffmpeg", {})

        self.rtmp_url = f"rtmp://{rtmp_cfg['host']}:{rtmp_cfg['port']}/{rtmp_cfg['app']}/{rtmp_cfg['key']}"
        self.ffmpeg_path = self._resolve_ffmpeg_path(ffmpeg_cfg.get("path", ""))
        self.video_codec = ffmpeg_cfg.get("video_codec", "copy")
        self.audio_codec = ffmpeg_cfg.get("audio_codec", "copy")
        self.video_bitrate = ffmpeg_cfg.get("video_bitrate", "")
        self.audio_bitrate = ffmpeg_cfg.get("audio_bitrate", "")
        self.loglevel = ffmpeg_cfg.get("loglevel", "warning")
        self.extra_args = ffmpeg_cfg.get("extra_args", "")
        self._process: Optional[subprocess.Popen] = None

    @staticmethod
    def _resolve_ffmpeg_path(config_path: str) -> str:
        """解析 FFmpeg 路径，优先使用配置路径，其次查找系统 PATH"""
        if config_path:
            if not os.path.isabs(config_path):
                config_path = os.path.abspath(config_path)
            if os.path.isfile(config_path):
                return config_path
            logger.warning(f"配置的 FFmpeg 路径不存在: {config_path}")
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg
        return "ffmpeg"

    @staticmethod
    def check_available(config: dict = None) -> bool:
        """检查 ffmpeg 是否可用"""
        if config:
            path = config.get("ffmpeg", {}).get("path", "")
            if path:
                if not os.path.isabs(path):
                    path = os.path.abspath(path)
                if os.path.isfile(path):
                    return True
        return shutil.which("ffmpeg") is not None

    def start(self, stdin_pipe):
        """
        启动 FFmpeg 进程
        stdin_pipe: streamlink 进程的 stdout（subprocess.Popen 的 stdout 管道）
        """
        if self._process and self._process.poll() is None:
            logger.warning("FFmpeg 进程已在运行")
            return

        cmd = self._build_command()
        logger.info(f"启动 FFmpeg: {' '.join(cmd)}")

        self._process = subprocess.Popen(
            cmd,
            stdin=stdin_pipe,       # 直接连接 streamlink 的 stdout
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        # 在后台线程中读取 stderr
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True
        )
        self._stderr_thread.start()

        logger.info(f"FFmpeg 已启动，推流目标: {self.rtmp_url}")

    def _build_command(self) -> list:
        """构建 FFmpeg 命令行"""
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-loglevel", self.loglevel,
            "-stats",
            "-i", "pipe:0",         # 从 stdin 读取
            "-c:v", self.video_codec,
            "-c:a", self.audio_codec,
        ]

        if self.video_bitrate and self.video_codec != "copy":
            cmd.extend(["-b:v", self.video_bitrate])
        if self.audio_bitrate and self.audio_codec != "copy":
            cmd.extend(["-b:a", self.audio_bitrate])

        cmd.extend(["-f", "flv"])

        if self.extra_args:
            cmd.extend(self.extra_args.split())

        cmd.append(self.rtmp_url)
        return cmd

    def _drain_stderr(self):
        """后台线程：持续读取 FFmpeg stderr"""
        try:
            for line in iter(self._process.stderr.readline, b""):
                text = line.decode(errors="replace").strip()
                if text:
                    if "frame=" in text or "bitrate=" in text:
                        logger.info(f"[ffmpeg] {text}")
                    else:
                        logger.debug(f"[ffmpeg] {text}")
        except Exception:
            pass

    @property
    def is_running(self) -> bool:
        """进程是否在运行"""
        return self._process is not None and self._process.poll() is None

    @property
    def returncode(self) -> Optional[int]:
        """进程退出码"""
        return self._process.returncode if self._process else None

    def stop(self):
        """停止 FFmpeg 进程"""
        if self._process and self._process.poll() is None:
            logger.info("正在停止 FFmpeg 进程...")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg 未响应 terminate，使用 kill")
                self._process.kill()
                self._process.wait()
            logger.info("FFmpeg 进程已停止")
        self._process = None
