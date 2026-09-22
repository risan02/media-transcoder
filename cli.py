#!/usr/bin/env python3
"""
media-transcoder 命令行入口。

示例：
  # 查看预设
  python cli.py presets

  # 单文件转码
  python cli.py convert input.mkv -p mp4-h264-balanced -o output.mp4

  # 提取音频
  python cli.py convert video.mp4 -p extract-audio -o song.mp3

  # 批量转码整个文件夹
  python cli.py batch ./movies -p mp4-h264-small -o ./movies_mp4

  # 查看文件信息
  python cli.py info input.mp4
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from transcoder.engine import Engine, Progress, TranscodeError, human_size
from transcoder.presets import list_presets, get_preset


def _print_progress(p: Progress, bar_width: int = 40) -> None:
    filled = int(bar_width * p.percent / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    speed = f" {p.speed:>6}" if p.speed else ""
    print(f"\r  [{bar}] {p.percent:5.1f}%{speed}", end="", flush=True)


def cmd_info(engine: Engine, args) -> int:
    path = Path(args.input)
    info = engine.probe(path)
    print(f"文件: {path}")
    print(f"大小: {human_size(path.stat().st_size)}")
    print(f"时长: {info.duration:.2f} 秒 ({int(info.duration//60)}分{int(info.duration%60)}秒)")
    print(f"总码率: {info.bit_rate/1000:.0f} kbps" if info.bit_rate else "总码率: N/A")
    print(f"视频: {'有' if info.has_video else '无'}  {info.size_label}  编码={info.video_codec or '-'}")
    print(f"音频: {'有' if info.has_audio else '无'}  编码={info.audio_codec or '-'}")
    return 0


def cmd_convert(engine: Engine, args) -> int:
    preset = get_preset(args.preset)
    inp = Path(args.input)
    if args.output:
        out = Path(args.output)
    else:
        out = inp.with_suffix(preset.ext)
    t0 = time.time()
    try:
        print(f"▶ 转码: {inp.name}")
        print(f"  预设: {preset.name} - {preset.description}")
        print(f"  输出: {out}")
        engine.transcode(inp, out, preset, on_progress=_print_progress)
        dt = time.time() - t0
        print()
        print(f"✓ 完成，耗时 {dt:.1f} 秒，输出大小 {human_size(out.stat().st_size)}")
        return 0
    except TranscodeError as e:
        print(f"\n✗ 失败: {e}", file=sys.stderr)
        return 1


def cmd_batch(engine: Engine, args) -> int:
    preset = get_preset(args.preset)
    files = engine.collect_inputs(args.input, recursive=not args.flat)
    if not files:
        print("未找到可转码的音视频文件。")
        return 1
    out_dir = Path(args.output) if args.output else Path(args.input)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"共发现 {len(files)} 个文件，预设: {preset.name}")
    ok = fail = skip = 0
    t0 = time.time()
    for i, f in enumerate(files, 1):
        out = out_dir / (f.stem + preset.ext)
        if out.exists() and not args.overwrite:
            print(f"[{i}/{len(files)}] 跳过（已存在）: {out.name}")
            skip += 1
            continue
        print(f"\n[{i}/{len(files)}] {f.name}")
        try:
            engine.transcode(f, out, preset, overwrite=args.overwrite,
                             on_progress=_print_progress)
            print(f"  ✓ -> {out.name}")
            ok += 1
        except TranscodeError as e:
            print(f"\n  ✗ {e}")
            fail += 1
    dt = time.time() - t0
    print(f"\n=== 完成：成功 {ok}，失败 {fail}，跳过 {skip}，总耗时 {dt:.1f} 秒 ===")
    return 0 if fail == 0 else 2


def cmd_presets(_engine: Engine, _args) -> int:
    print(list_presets())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transcoder",
        description="基于 FFmpeg 的音视频转码工具（自动下载 FFmpeg）",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("presets", help="列出所有预设")
    sp.set_defaults(func=cmd_presets)

    sp = sub.add_parser("info", help="查看媒体文件信息")
    sp.add_argument("input", help="输入文件路径")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("convert", help="单文件转码")
    sp.add_argument("input", help="输入文件路径")
    sp.add_argument("-p", "--preset", required=True, help="预设名称（见 presets）")
    sp.add_argument("-o", "--output", help="输出文件路径（默认与输入同目录，按预设后缀）")
    sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("batch", help="批量转码（文件或文件夹）")
    sp.add_argument("input", help="输入文件或文件夹")
    sp.add_argument("-p", "--preset", required=True, help="预设名称")
    sp.add_argument("-o", "--output", help="输出文件夹（默认与输入同目录）")
    sp.add_argument("--flat", action="store_true", help="不递归子文件夹")
    sp.add_argument("--overwrite", action="store_true", default=True, help="覆盖已存在文件")
    sp.set_defaults(func=cmd_batch)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    engine = Engine()
    try:
        return args.func(engine, args)
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.verbose:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
