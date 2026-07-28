# YouTube 直播转播

通过 streamlink + FFmpeg 将 YouTube 直播流转播到本地 RTMP 服务器，供 OBS 等软件使用。

## 核心特性

- **管道模式**：streamlink → FFmpeg 通过 pipe 连接，确保代理出口 IP 一致
- **自动重连**：断流时自动重启整个管道，指数退避重试
- **守护进程**：持续监控 streamlink 和 FFmpeg 进程状态
- **本地 RTMP 服务器**：内置 mediamtx，开箱即用

## 架构

```
YouTube CDN ←→ 代理(随机IP) ←→ streamlink ─pipe─→ FFmpeg ─RTMP─→ mediamtx ← OBS
                └──── 同一进程 ────┘                    本地        本地
```

**为什么用 pipe 模式？**

如果 yt-dlp/streamlink 获取 m3u8 URL 后，再让 FFmpeg 单独通过代理去拉流，两次代理请求的出口 IP 可能不同，导致 YouTube CDN 返回 403。pipe 模式下，streamlink 在同一进程内完成所有网络请求，HTTP 连接池复用同一 TCP 连接，出口 IP 不会变。

## 前置依赖

### 1. Python 3.10+

### 2. streamlink
```bash
pip install streamlink
```

### 3. FFmpeg
- **Windows**: `winget install ffmpeg` 或从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载
- **Mac**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

### 4. mediamtx（RTMP 服务器）

从 [GitHub Releases](https://github.com/bluenviron/mediamtx/releases) 下载对应平台版本：

- Windows: `mediamtx_vX.X.X_windows_amd64.zip`
- Mac (Intel): `mediamtx_vX.X.X_darwin_amd64.tar.gz`
- Mac (Apple Silicon): `mediamtx_vX.X.X_darwin_arm64.tar.gz`
- Linux: `mediamtx_vX.X.X_linux_amd64.tar.gz`

解压后放到 `mediamtx/` 目录下：
```
youtube-relay/
├── mediamtx/
│   ├── mediamtx.exe    (或 mediamtx)
│   └── mediamtx.yml
```

## 安装

```bash
cd youtube-relay
pip install -r requirements.txt
```

## 配置

编辑 `config.yaml`：

```yaml
# 必填项
proxy: "http://127.0.0.1:7890"          # 你的本地代理地址
youtube_url: "https://www.youtube.com/watch?v=XXXXX"  # 直播地址

# 可选项
quality: "best"                          # 画质偏好
```

## 使用

### 启动转播

```bash
python main.py
```

### OBS 中使用

1. 添加「媒体源」
2. 取消勾选「本地文件」
3. 输入地址：`rtmp://localhost/live/youtube`
4. 点击确定

### 停止

按 `Ctrl+C` 停止程序

## 重连机制

| 情况 | 处理方式 |
|------|---------|
| streamlink 进程退出 | 停止 FFmpeg → 重新启动整个管道 |
| FFmpeg 进程退出 | 停止 streamlink → 重新启动整个管道 |
| 代理不可用 | 等待 → 指数退避重试 |
| 直播未开始 | streamlink 内置等待直播开始 |
| 稳定运行 >2min | 重置重连计数，退避延迟回到初始值 |

重连退避策略：3s → 6s → 12s → 24s → 48s → 60s（上限）

## 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| proxy | - | 本地代理地址 |
| youtube_url | - | YouTube 直播地址 |
| quality | best | 画质偏好 |
| rtmp.host | localhost | RTMP 服务器地址 |
| rtmp.port | 1935 | RTMP 端口 |
| rtmp.app | live | RTMP app 名 |
| rtmp.key | youtube | 流密钥 |
| reconnect.max_retries | 0 | 最大重试次数（0=无限） |
| reconnect.initial_delay | 3 | 首次重连延迟 |
| reconnect.max_delay | 60 | 最大重连延迟 |
| ffmpeg.video_codec | copy | 视频编码（copy=不转码） |
| ffmpeg.audio_codec | copy | 音频编码（copy=不转码） |

## 常见问题

### Q: 代理出口 IP 是随机的，会影响使用吗？

不会。每次重连时，streamlink 会以新的代理连接重新获取直播流 URL，整个管道作为新的 session，不存在 IP 不匹配问题。管道运行期间，streamlink 复用同一连接，出口 IP 不会变。

### Q: 直播还没开始怎么办？

streamlink 内置 `--retry-streams` 参数，会自动等待直播开始，无需额外处理。

### Q: 转播延迟多少？

通常 5-15 秒，取决于 YouTube 直播本身的延迟和转播链路。使用 `copy` 编码（不转码）延迟最低。

### Q: 不想用 mediamtx 怎么办？

可以使用任何 RTMP 服务器，只需修改 config.yaml 中的 rtmp 配置指向你的服务器即可。例如 nginx-rtmp、SRS 等。
