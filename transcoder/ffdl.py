"""
FFmpeg 二进制定位与自动下载。

查找顺序：
1. 系统 PATH 中的 ffmpeg / ffprobe
2. 环境变量 FFMPEG_PATH / FFPROBE_PATH
3. imageio-ffmpeg 包自带的 ffmpeg 二进制（pip install imageio-ffmpeg）
4. 首次使用时自动从官方 GitHub 下载静态编译版到用户缓存目录
"""
from __future__ import annotations

import os
import shutil
import sys
import stat
import logging
import platform
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# 用户缓存目录
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "media-transcoder" / "ffmpeg"

# 官方静态构建（BtbN/FFmpeg-Builds）
FFMPEG_DOWNLOAD = {
    "Windows": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "Linux": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
    "Darwin": "https://evermeet.cx/ffmpeg/getrelease/zip",  # macOS
}


def _is_executable(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK if os.name != "nt" else os.R_OK)


def _find_in_path(name: str) -> Optional[str]:
    exe = shutil.which(name)
    return exe


def _find_in_imageio() -> Tuple[Optional[str], Optional[str]]:
    """从 imageio-ffmpeg 包中提取 ffmpeg 路径（它不提供 ffprobe，但提供 ffmpeg）。"""
    try:
        import imageio_ffmpeg  # type: ignore
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        return ff, None
    except Exception:
        return None, None


def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("正在下载 FFmpeg: %s", url)
    log.info("保存到: %s", dest)
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        total = resp.headers.get("Content-Length")
        total = int(total) if total else None
        downloaded = 0
        block = 1024 * 64
        while True:
            chunk = resp.read(block)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 / total
                print(f"\r下载进度: {pct:5.1f}%  ({downloaded//1024//1024} MB)", end="", flush=True)
    print()


def _extract_ffmpeg(archive: Path, cache_dir: Path) -> None:
    """从下载的压缩包中解压 ffmpeg.exe / ffprobe.exe 到 cache_dir。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            for member in z.namelist():
                name = os.path.basename(member)
                if name.lower() in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
                    target = cache_dir / name
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    try:
                        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                    except Exception:
                        pass
                    log.info("已解压: %s", target)
    else:
        # .tar.xz 等：调用系统 tar（Windows 10+ 自带 bsdtar）
        log.info("解压 %s ...", archive)
        shutil.unpack_archive(str(archive), extract_dir=str(cache_dir))


def ensure_ffmpeg(download: bool = True) -> Tuple[str, str]:
    """
    返回 (ffmpeg_path, ffprobe_path)。找不到且不允许下载时抛 RuntimeError。
    """
    # 1. 环境变量
    env_ff = os.environ.get("FFMPEG_PATH")
    env_fp = os.environ.get("FFPROBE_PATH")
    if env_ff and Path(env_ff).is_file():
        return env_ff, env_fp or "ffprobe"

    # 2. PATH
    ff = _find_in_path("ffmpeg")
    fp = _find_in_path("ffprobe")
    if ff:
        return ff, fp or "ffprobe"

    # 3. imageio-ffmpeg
    ff, fp = _find_in_imageio()
    if ff:
        return ff, fp or "ffprobe"

    # 4. 缓存目录
    cache_ff = CACHE_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    cache_fp = CACHE_DIR / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if cache_ff.is_file():
        return str(cache_ff), str(cache_fp) if cache_fp.is_file() else "ffprobe"

    # 5. 自动下载
    if not download:
        raise RuntimeError(
            "未找到 FFmpeg。请执行以下任一操作：\n"
            "  1) 使用 pip install imageio-ffmpeg\n"
            "  2) 安装 FFmpeg 并加入 PATH\n"
            "  3) 设置环境变量 FFMPEG_PATH 指向 ffmpeg 可执行文件"
        )

    system = platform.system()
    url = FFMPEG_DOWNLOAD.get(system)
    if not url:
        raise RuntimeError(f"暂不支持自动下载 {system} 平台的 FFmpeg，请手动安装。")

    suffix = ".zip" if system == "Windows" else ".tar.xz"
    archive = CACHE_DIR / f"ffmpeg-download{suffix}"
    _download_file(url, archive)
    _extract_ffmpeg(archive, CACHE_DIR)
    try:
        archive.unlink()
    except Exception:
        pass

    if cache_ff.is_file():
        return str(cache_ff), str(cache_fp) if cache_fp.is_file() else "ffprobe"
    raise RuntimeError("FFmpeg 下载解压后仍未找到 ffmpeg 可执行文件。")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ff, fp = ensure_ffmpeg(download=True)
    print("ffmpeg :", ff)
    print("ffprobe:", fp)
