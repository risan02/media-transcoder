"""
核心转码引擎：调用 FFmpeg / FFprobe，解析进度，批量处理。
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .ffdl import ensure_ffmpeg
from .presets import Preset

log = logging.getLogger(__name__)

# 常见音视频扩展名
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
              ".m4v", ".mpg", ".mpeg", ".ts", ".3gp", ".rmvb", ".rm", ".m2ts"}
AUDIO_EXTS = {".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".wma",
              ".opus", ".ape", ".aiff", ".mka"}


@dataclass
class MediaInfo:
    duration: float = 0.0       # 秒
    width: int = 0
    height: int = 0
    video_codec: str = ""
    audio_codec: str = ""
    bit_rate: int = 0          # bps
    has_video: bool = False
    has_audio: bool = False

    @property
    def size_label(self) -> str:
        return f"{self.width}x{self.height}" if self.width else "N/A"


@dataclass
class Progress:
    percent: float      # 0-100
    speed: str = ""     # 例如 "1.5x"
    time: str = ""      # 已处理时间
    message: str = ""


ProgressCallback = Callable[[Progress], None]


class TranscodeError(RuntimeError):
    pass


class Engine:
    def __init__(self, ffmpeg: Optional[str] = None, ffprobe: Optional[str] = None):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self._ready = False

    def _ensure(self):
        if self._ready:
            return
        self.ffmpeg, self.ffprobe = ensure_ffmpeg(
            download=True,
        )
        self._ready = True
        log.debug("ffmpeg=%s ffprobe=%s", self.ffmpeg, self.ffprobe)

    # ---------- 媒体信息 ----------
    def probe(self, input_path: str | Path) -> MediaInfo:
        self._ensure()
        input_path = str(input_path)
        # 优先使用 ffprobe（结构化 JSON）
        if self.ffprobe and Path(self.ffprobe).is_file():
            try:
                return self._probe_with_ffprobe(input_path)
            except Exception as e:
                log.warning("ffprobe 失败，降级使用 ffmpeg 解析: %s", e)
        # 降级：用 ffmpeg -i 解析 stderr 文本
        return self._probe_with_ffmpeg(input_path)

    def _probe_with_ffprobe(self, input_path: str) -> MediaInfo:
        cmd = [
            self.ffprobe, "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            input_path,
        ]
        log.debug("运行: %s", " ".join(cmd))
        out = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
        if out.returncode != 0:
            raise TranscodeError(f"ffprobe 失败: {out.stderr.strip()}")
        data = json.loads(out.stdout or "{}")
        info = MediaInfo()
        fmt = data.get("format", {})
        info.duration = float(fmt.get("duration", 0) or 0)
        info.bit_rate = int(fmt.get("bit_rate", 0) or 0)
        for s in data.get("streams", []):
            if s.get("codec_type") == "video" and not info.has_video:
                info.has_video = True
                info.video_codec = s.get("codec_name", "")
                info.width = int(s.get("width", 0) or 0)
                info.height = int(s.get("height", 0) or 0)
            elif s.get("codec_type") == "audio" and not info.has_audio:
                info.has_audio = True
                info.audio_codec = s.get("codec_name", "")
        return info

    def _probe_with_ffmpeg(self, input_path: str) -> MediaInfo:
        """ffprobe 不可用时的降级方案：解析 `ffmpeg -i <file>` 的 stderr。"""
        cmd = [self.ffmpeg, "-hide_banner", "-i", input_path]
        creationflags = 0
        if os.name == "nt":
            creationflags = 0x08000000
        # ffmpeg -i 不带输出会以非零退出（因为没有输出文件），这是正常的
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              creationflags=creationflags, timeout=30)
        text = (proc.stderr or "") + (proc.stdout or "")
        info = MediaInfo()
        # Duration: 00:00:05.00, start: 0.000000, bitrate: 123 kb/s
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if m:
            info.duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        m = re.search(r"bitrate:\s*(\d+)\s*kb/s", text)
        if m:
            info.bit_rate = int(m.group(1)) * 1000
        # Stream #0:0[0x1](und): Video: h264 (High) ..., yuv420p, 320x240 [SAR ...]
        for line in text.splitlines():
            if ": Video:" in line:
                info.has_video = True
                mv = re.search(r"Video:\s*(\w+)", line)
                if mv:
                    info.video_codec = mv.group(1)
                ms = re.search(r"(\d{2,5})x(\d{2,5})", line)
                if ms:
                    info.width = int(ms.group(1))
                    info.height = int(ms.group(2))
            elif ": Audio:" in line:
                info.has_audio = True
                ma = re.search(r"Audio:\s*(\w+)", line)
                if ma:
                    info.audio_codec = ma.group(1)
        return info

    # ---------- 转码 ----------
    def transcode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        preset: Preset,
        overwrite: bool = True,
        on_progress: Optional[ProgressCallback] = None,
        extra_args: Optional[List[str]] = None,
    ) -> Path:
        self._ensure()
        input_path = Path(input_path)
        output_path = Path(output_path)
        if not input_path.is_file():
            raise TranscodeError(f"输入文件不存在: {input_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 先 probe 时长用于进度计算
        try:
            info = self.probe(input_path)
            total = info.duration
        except Exception as e:
            log.warning("probe 失败，进度将不可用: %s", e)
            total = 0.0

        cmd: List[str] = [
            self.ffmpeg, "-hide_banner", "-y" if overwrite else "-n",
            "-i", str(input_path),
        ]
        cmd += preset.build_args()
        if extra_args:
            cmd += extra_args
        cmd += ["-stats", str(output_path)]

        log.info("运行: %s", " ".join(cmd))
        # Windows 下隐藏控制台窗口
        creationflags = 0
        if os.name == "nt":
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=creationflags,
        )

        time_re = re.compile(r"time=(\d+:\d+:\d+\.\d+)")
        speed_re = re.compile(r"speed=\s*([0-9\.]+x)")
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if on_progress and total > 0:
                    mt = time_re.search(line)
                    ms = speed_re.search(line)
                    if mt:
                        h, m, s = mt.group(1).split(":")
                        cur = int(h) * 3600 + int(m) * 60 + float(s)
                        pct = min(100.0, cur / total * 100.0)
                        on_progress(Progress(
                            percent=pct,
                            speed=ms.group(1) if ms else "",
                            time=mt.group(1),
                            message=line,
                        ))
                log.debug("ffmpeg: %s", line)
        finally:
            ret = proc.wait()

        if ret != 0:
            raise TranscodeError(
                f"转码失败（退出码 {ret}）。请检查输入文件或预设参数。"
            )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise TranscodeError("转码完成但输出文件为空或未生成。")
        return output_path

    # ---------- 批量 ----------
    def collect_inputs(self, path: str | Path, recursive: bool = True) -> List[Path]:
        path = Path(path)
        if path.is_file():
            return [path]
        if not path.is_dir():
            raise TranscodeError(f"路径不存在: {path}")
        exts = VIDEO_EXTS | AUDIO_EXTS
        files: List[Path] = []
        iterator = path.rglob("*") if recursive else path.iterdir()
        for p in iterator:
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
        return sorted(files)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
