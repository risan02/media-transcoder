"""
转码预设方案。每个预设定义：视频编码器、音频编码器、码率、容器扩展名、说明。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Preset:
    name: str
    description: str
    # ffmpeg 参数（不含 -i 输入 和 输出路径）
    vcodec: Optional[str] = None        # 例如 libx264, libx265, copy
    acodec: Optional[str] = None        # 例如 aac, libmp3lame, flac, copy
    vbitrate: Optional[str] = None    # 例如 "2M"
    abitrate: Optional[str] = None    # 例如 "192k"
    resolution: Optional[str] = None   # 例如 "1280:720"，None 表示保持
    fps: Optional[int] = None          # 帧率，None 表示保持
    ext: str = ".mp4"                  # 默认输出扩展名
    extra_args: List[str] = field(default_factory=list)
    audio_only: bool = False           # 是否只输出音频
    pix_fmt: Optional[str] = None      # 像素格式，例如 yuv420p

    def build_args(self) -> List[str]:
        args: List[str] = []
        if self.audio_only:
            args += ["-vn"]
        else:
            if self.vcodec:
                args += ["-c:v", self.vcodec]
            if self.vbitrate:
                args += ["-b:v", self.vbitrate]
            if self.resolution:
                args += ["-vf", f"scale={self.resolution}"]
            if self.fps:
                args += ["-r", str(self.fps)]
            if self.pix_fmt:
                args += ["-pix_fmt", self.pix_fmt]
        if self.acodec:
            args += ["-c:a", self.acodec]
        if self.abitrate:
            args += ["-b:a", self.abitrate]
        args += self.extra_args
        return args


PRESETS: Dict[str, Preset] = {
    # ===== 视频 =====
    "mp4-h264-high": Preset(
        name="mp4-h264-high",
        description="MP4 / H.264 高画质（CRF 18，质量优先）",
        vcodec="libx264", acodec="aac", abitrate="192k",
        ext=".mp4", pix_fmt="yuv420p",
        extra_args=["-crf", "18", "-preset", "medium", "-movflags", "+faststart"],
    ),
    "mp4-h264-balanced": Preset(
        name="mp4-h264-balanced",
        description="MP4 / H.264 均衡（CRF 23，体积与质量平衡）",
        vcodec="libx264", acodec="aac", abitrate="128k",
        ext=".mp4", pix_fmt="yuv420p",
        extra_args=["-crf", "23", "-preset", "medium", "-movflags", "+faststart"],
    ),
    "mp4-h264-small": Preset(
        name="mp4-h264-small",
        description="MP4 / H.264 小体积（CRF 28，适合分享）",
        vcodec="libx264", acodec="aac", abitrate="96k",
        ext=".mp4", pix_fmt="yuv420p",
        extra_args=["-crf", "28", "-preset", "fast", "-movflags", "+faststart"],
    ),
    "mp4-h265": Preset(
        name="mp4-h265",
        description="MP4 / H.265 (HEVC) 高压缩率（体积更小）",
        vcodec="libx265", acodec="aac", abitrate="128k",
        ext=".mp4", pix_fmt="yuv420p",
        extra_args=["-crf", "26", "-preset", "medium", "-tag:v", "hvc1"],
    ),
    "webm-vp9": Preset(
        name="webm-vp9",
        description="WebM / VP9（网页通用，高压缩）",
        vcodec="libvpx-vp9", acodec="libopus", abitrate="128k",
        ext=".webm",
        extra_args=["-crf", "30", "-b:v", "0"],
    ),
    "mov-prores": Preset(
        name="mov-prores",
        description="MOV / ProRes 422（剪辑用，无损画质）",
        vcodec="prores_ks", acodec="pcm_s16le",
        ext=".mov",
        extra_args=["-profile:v", "2"],
    ),
    "gif": Preset(
        name="gif",
        description="GIF 动图（24fps，宽 480）",
        vcodec="gif",
        ext=".gif", fps=15, resolution="480:-1",
        extra_args=["-loop", "0"],
    ),

    # ===== 音频 =====
    "mp3-320": Preset(
        name="mp3-320",
        description="MP3 320kbps（高质量）",
        acodec="libmp3lame", abitrate="320k",
        ext=".mp3", audio_only=True,
    ),
    "mp3-256": Preset(
        name="mp3-256",
        description="MP3 256kbps（推荐）",
        acodec="libmp3lame", abitrate="256k",
        ext=".mp3", audio_only=True,
    ),
    "mp3-192": Preset(
        name="mp3-192",
        description="MP3 192kbps（均衡）",
        acodec="libmp3lame", abitrate="192k",
        ext=".mp3", audio_only=True,
    ),
    "mp3-128": Preset(
        name="mp3-128",
        description="MP3 128kbps（小体积）",
        acodec="libmp3lame", abitrate="128k",
        ext=".mp3", audio_only=True,
    ),
    "aac-256": Preset(
        name="aac-256",
        description="AAC 256kbps（兼容 iOS/Android）",
        acodec="aac", abitrate="256k",
        ext=".m4a", audio_only=True,
    ),
    "flac": Preset(
        name="flac",
        description="FLAC 无损压缩",
        acodec="flac",
        ext=".flac", audio_only=True,
    ),
    "wav-pcm": Preset(
        name="wav-pcm",
        description="WAV 未压缩 PCM",
        acodec="pcm_s16le",
        ext=".wav", audio_only=True,
    ),
    "ogg-vorbis": Preset(
        name="ogg-vorbis",
        description="OGG / Vorbis（开源音频）",
        acodec="libvorbis", abitrate="192k",
        ext=".ogg", audio_only=True,
    ),

    # ===== 提取音轨 =====
    "extract-audio": Preset(
        name="extract-audio",
        description="从视频中提取音轨（MP3 320k）",
        acodec="libmp3lame", abitrate="320k",
        ext=".mp3", audio_only=True,
    ),
    "copy-stream": Preset(
        name="copy-stream",
        description="直接复制流（仅改封装，速度极快）",
        vcodec="copy", acodec="copy",
        ext=".mkv",
    ),
}


def list_presets() -> str:
    lines = ["可用预设：", f"{'名称':<22} {'说明'}", "-" * 60]
    for k, v in PRESETS.items():
        lines.append(f"{k:<22} {v.description}")
    return "\n".join(lines)


def get_preset(name: str) -> Preset:
    if name not in PRESETS:
        raise KeyError(f"预设 '{name}' 不存在。\n\n{list_presets()}")
    return PRESETS[name]
