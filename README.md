# Media Transcoder

基于 FFmpeg 的跨平台音视频转码工具，提供深色极简图形界面和命令行两种使用方式。开箱即用，自动下载 FFmpeg，无需手动配置环境。

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

## 功能特性

- **图形界面**：深色极简设计，拖拽导入，批量处理，实时进度
- **命令行**：支持脚本化批量转码，适合自动化场景
- **自动 FFmpeg**：首次运行自动检测/下载 FFmpeg，无需手动安装
- **17 种预设**：H.264 / H.265 / WebM / ProRes / GIF / MP3 / AAC / FLAC / WAV 等
- **每文件独立设置**：混合导入不同格式文件，可分别指定输出预设
- **灵活输出**：自定义输出目录，完成后一键打开
- **跨平台**：Windows / macOS / Linux

## 快速开始

### 从 Release 下载（推荐普通用户）

前往 [Releases](../../releases) 下载 `MediaTranscoder.exe`（Windows），双击即用，无需安装 Python。

### 从源码运行

```bash
git clone https://github.com/<your-username>/media-transcoder.git
cd media-transcoder
pip install -r requirements.txt
python gui.py
```

## 使用说明

### 图形界面

1. **添加文件**：拖拽文件到虚线区域，或点击区域选择文件，支持批量
2. **设置预设**：
   - 底部「默认格式」选择新文件的默认输出格式
   - 每个文件行右侧的下拉框可单独指定预设
   - 「应用到全部」一键批量设置
3. **输出位置**：默认输出到 `源文件目录/transcoded/`，可点「浏览…」修改
4. **开始转码**：点击「开始转码」，进度条实时显示，完成后可点「打开」查看结果
5. **移除文件**：点文件行右侧的 ✕ 按钮

### 命令行

```bash
python cli.py presets                              # 查看所有预设
python cli.py info input.mkv                       # 查看媒体信息
python cli.py convert input.mkv -p mp4-h264-balanced   # 单文件转码
python cli.py convert video.mp4 -p extract-audio    # 提取音频
python cli.py batch ./movies -p mp4-h264-small -o ./output  # 批量转码
```

## 预设列表

### 视频
| 预设 | 说明 |
|---|---|
| `mp4-h264-high` | MP4 / H.264 高画质（CRF 18） |
| `mp4-h264-balanced` | MP4 / H.264 均衡（CRF 23） |
| `mp4-h264-small` | MP4 / H.264 小体积（CRF 28） |
| `mp4-h265` | MP4 / H.265 (HEVC) |
| `webm-vp9` | WebM / VP9 |
| `mov-prores` | MOV / ProRes 422 |
| `gif` | GIF 动图 |

### 音频
| 预设 | 说明 |
|---|---|
| `mp3-320` / `mp3-256` / `mp3-192` / `mp3-128` | MP3 不同码率 |
| `aac-256` | AAC / M4A |
| `flac` | FLAC 无损 |
| `wav-pcm` | WAV 未压缩 |
| `ogg-vorbis` | OGG / Vorbis |
| `extract-audio` | 从视频提取 MP3 音轨 |
| `copy-stream` | 直接复制流（改封装，极快） |

## 构建 EXE（Windows）

```bash
pip install pyinstaller customtkinter tkinterdnd2 imageio-ffmpeg

pyinstaller --onefile --windowed --name MediaTranscoder \
  --collect-all imageio_ffmpeg \
  --collect-all customtkinter \
  --collect-all tkinterdnd2 \
  gui.py
```

生成的 exe 在 `dist/MediaTranscoder.exe`。

## 项目结构

```
media-transcoder/
├── gui.py                  # 图形界面入口（customtkinter）
├── cli.py                  # 命令行入口
├── requirements.txt        # Python 依赖
├── README.md
├── LICENSE
└── transcoder/             # 核心包
    ├── __init__.py
    ├── engine.py            # FFmpeg 调用、进度解析、批量处理
    ├── presets.py           # 预设定义
    └── ffdl.py              # FFmpeg 自动定位与下载
```

## 技术栈

- **FFmpeg**：音视频编解码核心
- **customtkinter**：现代深色 UI 框架
- **tkinterdnd2**：拖拽文件支持
- **imageio-ffmpeg**：内置 FFmpeg 二进制

## License

[MIT](LICENSE)
