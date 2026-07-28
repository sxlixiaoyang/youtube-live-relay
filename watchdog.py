"""
守护进程 + 自动重连
监控 streamlink + FFmpeg 管道，异常时自动重建整个管道
"""

import asyncio
import logging
import time
from typing import Optional

from stream_fetcher import StreamFetcher
from ffmpeg_relay import FfmpegRelay

logger = logging.getLogger("watchdog")


class Watchdog:
    """守护进程：监控管道状态，异常时重连"""

    def __init__(self, config: dict, cookies_file: str = ""):
        self.config = config
        self.cookies_file = cookies_file
        self.fetcher = StreamFetcher(config, cookies_file=cookies_file)
        self.relay = FfmpegRelay(config)

        rc = config.get("reconnect", {})
        self.max_retries = rc.get("max_retries", 0)
        self.initial_delay = rc.get("initial_delay", 3)
        self.max_delay = rc.get("max_delay", 60)
        self.backoff_factor = rc.get("backoff_factor", 2)

        self._retry_count = 0
        self._current_delay = self.initial_delay
        self._running = False
        self._start_time = 0
        # 成功运行多久后重置重连计数（秒）
        self._stable_threshold = 120

    async def start(self):
        """启动守护进程主循环"""
        self._running = True
        logger.info("守护进程启动")

        while self._running:
            try:
                await self._run_pipeline()
            except Exception as e:
                logger.error(f"管道异常: {e}")

            if not self._running:
                break

            # 管道退出，处理重连逻辑
            should_retry = await self._handle_reconnect()
            if not should_retry:
                break

        logger.info("守护进程已停止")

    async def _run_pipeline(self):
        """启动并监控 streamlink → FFmpeg 管道"""
        self._start_time = time.time()

        # 1. 启动 streamlink
        streamlink_proc = self.fetcher.start()

        # 2. 启动 FFmpeg，stdin 直接连接 streamlink 的 stdout
        self.relay.start(streamlink_proc.stdout)

        # 3. 在 asyncio 中轮询进程状态
        while self._running:
            fetcher_alive = self.fetcher.is_running
            relay_alive = self.relay.is_running

            if not fetcher_alive:
                fetcher_code = self.fetcher.returncode
                logger.error(f"streamlink 已退出 (exit code: {fetcher_code})")
                break

            if not relay_alive:
                relay_code = self.relay.returncode
                logger.error(f"FFmpeg 已退出 (exit code: {relay_code})")
                break

            # 稳定运行超过阈值，重置重连计数
            elapsed = time.time() - self._start_time
            if elapsed > self._stable_threshold and self._retry_count > 0:
                logger.info(f"管道稳定运行 {self._stable_threshold}s，重置重连计数")
                self._retry_count = 0
                self._current_delay = self.initial_delay

            await asyncio.sleep(3)

        # 管道退出，清理进程
        self._stop_pipeline()

    async def _handle_reconnect(self) -> bool:
        """处理重连逻辑，返回是否应该重试"""
        self._retry_count += 1

        if self.max_retries > 0 and self._retry_count > self.max_retries:
            logger.error(f"已达到最大重试次数 ({self.max_retries})，停止重连")
            return False

        logger.info(
            f"等待 {self._current_delay}s 后重连 (第 {self._retry_count} 次重试)"
        )
        await asyncio.sleep(self._current_delay)

        # 指数退避
        self._current_delay = min(
            self._current_delay * self.backoff_factor,
            self.max_delay,
        )

        return True

    def _stop_pipeline(self):
        """停止整个管道"""
        # 先停 FFmpeg（消费者），再停 streamlink（生产者）
        self.relay.stop()
        self.fetcher.stop()

    async def stop(self):
        """停止守护进程"""
        logger.info("正在停止守护进程...")
        self._running = False
        self._stop_pipeline()

    def reset(self):
        """重置内部状态，以便重新启动"""
        self._stop_pipeline()
        self._retry_count = 0
        self._current_delay = self.initial_delay
        self._running = False
        self._start_time = 0
        # 重建 fetcher 和 relay，避免残留的进程状态
        self.fetcher = StreamFetcher(self.config, cookies_file=self.cookies_file)
        self.relay = FfmpegRelay(self.config)
        logger.info("Watchdog 已重置，可以重新启动")

    @property
    def retry_count(self) -> int:
        return self._retry_count

    @property
    def is_running(self) -> bool:
        return self._running
