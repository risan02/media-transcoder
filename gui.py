#!/usr/bin/env python3
"""
Media Transcoder - 深色极简 UI（customtkinter）
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog
from tkinterdnd2 import DND_FILES
from tkinterdnd2.TkinterDnD import _require as _require_dnd

from transcoder.engine import Engine, Progress, TranscodeError
from transcoder.presets import PRESETS

# ===== 设计令牌 =====
COLORS = {
    "bg": "#0a0a0a",
    "surface": "#141414",
    "elevated": "#1c1c1c",
    "hover": "#242424",
    "border": "#2a2a2a",
    "border_strong": "#3a3a3a",
    "text": "#ffffff",
    "text_2": "#8a8a8a",
    "text_3": "#555555",
}

# 所有预设：(显示名, preset_key)
ALL_PRESETS = [
    ("MP4 · H.264 高画质",   "mp4-h264-high"),
    ("MP4 · H.264 均衡",     "mp4-h264-balanced"),
    ("MP4 · H.264 小体积",   "mp4-h264-small"),
    ("MP4 · H.265",          "mp4-h265"),
    ("WebM · VP9",            "webm-vp9"),
    ("MOV · ProRes",         "mov-prores"),
    ("GIF 动图",              "gif"),
    ("MP3 · 320kbps",        "mp3-320"),
    ("MP3 · 256kbps",        "mp3-256"),
    ("MP3 · 192kbps",        "mp3-192"),
    ("MP3 · 128kbps",        "mp3-128"),
    ("AAC / M4A 256k",       "aac-256"),
    ("FLAC 无损",             "flac"),
    ("WAV 未压缩",           "wav-pcm"),
    ("OGG / Vorbis",         "ogg-vorbis"),
    ("提取音轨 → MP3",        "extract-audio"),
    ("复制流（改封装）",      "copy-stream"),
]
PRESET_LABELS = [label for label, _ in ALL_PRESETS]
LABEL_TO_KEY = {label: key for label, key in ALL_PRESETS}
KEY_TO_LABEL = {key: label for label, key in ALL_PRESETS}


class TranscoderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        _require_dnd(self)
        ctk.set_appearance_mode("dark")
        self.title("转码")
        self.geometry("720x780")
        self.minsize(560, 640)
        self.configure(fg_color=COLORS["bg"])

        self.engine = Engine()
        self.file_list: list[Path] = []
        self.file_presets: dict[Path, str] = {}
        self.file_outputs: dict[Path, Path] = {}
        self.file_widgets: dict[Path, dict] = {}
        self.msg_queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_flag = threading.Event()
        self.default_preset_key = "mp4-h264-balanced"
        self.output_dir: Path | None = None  # None = 自动（源文件/transcoded/）

        self._build_ui()
        self._setup_dnd()
        self.after(100, self._poll_queue)

    # ---------- UI ----------
    def _build_ui(self):
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=16)
        for r in range(5):
            self.container.grid_rowconfigure(r, weight=0)
        self.container.grid_rowconfigure(2, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Row 0: 顶栏
        topbar = ctk.CTkFrame(self.container, fg_color="transparent")
        topbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(topbar, text="转码", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=COLORS["text"]).pack(side="left")
        ctk.CTkLabel(topbar, text="v1.1", font=ctk.CTkFont(size=12),
                     text_color=COLORS["text_3"]).pack(side="right")

        # Row 1: 拖拽区
        self.dropzone = ctk.CTkFrame(
            self.container, fg_color=COLORS["surface"],
            border_width=2, border_color=COLORS["border_strong"],
            corner_radius=12, height=120,
        )
        self.dropzone.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.dropzone.grid_propagate(False)
        inner = ctk.CTkFrame(self.dropzone, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(inner, text="↓", font=ctk.CTkFont(size=28),
                     text_color=COLORS["text_3"]).pack()
        ctk.CTkLabel(inner, text="拖入文件", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLORS["text"]).pack(pady=(4, 2))
        ctk.CTkLabel(inner, text="或点击选择文件，支持批量", font=ctk.CTkFont(size=12),
                     text_color=COLORS["text_2"]).pack()
        self.dropzone.bind("<Button-1>", lambda e: self._pick_files())
        inner.bind("<Button-1>", lambda e: self._pick_files())

        # Row 2: 文件列表（伸缩区，固定最小高度）
        self.file_list_frame = ctk.CTkScrollableFrame(
            self.container, fg_color="transparent", height=220,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_strong"],
        )
        self.file_list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self._empty_hint = ctk.CTkLabel(
            self.file_list_frame, text="暂无文件",
            font=ctk.CTkFont(size=13), text_color=COLORS["text_3"],
        )
        self._empty_hint.pack(pady=30)

        # Row 3: 设置区（默认格式 + 输出目录）
        settings = ctk.CTkFrame(self.container, fg_color="transparent")
        settings.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        # 默认格式行
        row1 = ctk.CTkFrame(settings, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row1, text="默认格式", font=ctk.CTkFont(size=12),
                     text_color=COLORS["text_2"], width=70).pack(side="left")
        self.default_preset_menu = ctk.CTkOptionMenu(
            row1, values=PRESET_LABELS, width=220, height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["elevated"], button_color=COLORS["border_strong"],
            button_hover_color=COLORS["hover"], text_color=COLORS["text"],
            dropdown_fg_color=COLORS["elevated"], dropdown_hover_color=COLORS["hover"],
            dropdown_text_color=COLORS["text"],
            command=lambda choice: self._on_default_preset(choice),
        )
        self.default_preset_menu.set(KEY_TO_LABEL[self.default_preset_key])
        self.default_preset_menu.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row1, text="应用到全部", width=80, height=28,
            fg_color="transparent", border_width=1, border_color=COLORS["border"],
            hover_color=COLORS["hover"], text_color=COLORS["text_2"],
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._apply_to_all,
        ).pack(side="left")

        # 输出目录行
        row2 = ctk.CTkFrame(settings, fg_color="transparent")
        row2.pack(fill="x")
        ctk.CTkLabel(row2, text="输出位置", font=ctk.CTkFont(size=12),
                     text_color=COLORS["text_2"], width=70).pack(side="left")
        self.output_dir_var = ctk.StringVar(value="自动（源文件 / transcoded/）")
        self.output_dir_label = ctk.CTkLabel(
            row2, textvariable=self.output_dir_var,
            font=ctk.CTkFont(size=12), text_color=COLORS["text_3"],
            anchor="w",
        )
        self.output_dir_label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            row2, text="浏览…", width=60, height=28,
            fg_color="transparent", border_width=1, border_color=COLORS["border"],
            hover_color=COLORS["hover"], text_color=COLORS["text_2"],
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._pick_output_dir,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            row2, text="打开", width=50, height=28,
            fg_color="transparent", border_width=1, border_color=COLORS["border"],
            hover_color=COLORS["hover"], text_color=COLORS["text_2"],
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._open_output_dir,
        ).pack(side="right")

        # Row 4: 底部操作区
        self.footer = ctk.CTkFrame(self.container, fg_color=COLORS["surface"], corner_radius=8)
        self.footer.grid(row=4, column=0, sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.footer, text="就绪", font=ctk.CTkFont(size=12),
            text_color=COLORS["text_3"], anchor="w",
        )
        self.status_label.pack(fill="x", padx=14, pady=(10, 4))

        self.progress = ctk.CTkProgressBar(
            self.footer, height=4, corner_radius=2,
            fg_color=COLORS["elevated"], progress_color=COLORS["text"],
        )
        self.progress.pack(fill="x", padx=14, pady=(0, 10))
        self.progress.set(0)

        btn_row = ctk.CTkFrame(self.footer, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        self.cancel_btn = ctk.CTkButton(
            btn_row, text="取消", width=72, height=34,
            fg_color="transparent", border_width=1, border_color=COLORS["border"],
            hover_color=COLORS["hover"], text_color=COLORS["text_2"],
            font=ctk.CTkFont(size=13), corner_radius=6,
            command=self._cancel, state="disabled",
        )
        self.cancel_btn.pack(side="right", padx=(8, 0))
        self.start_btn = ctk.CTkButton(
            btn_row, text="开始转码", height=34,
            fg_color=COLORS["text"], hover_color="#e0e0e0",
            text_color=COLORS["bg"], font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=6, command=self._start,
        )
        self.start_btn.pack(side="right", fill="x", expand=True)

    def _setup_dnd(self):
        try:
            self.dropzone.drop_target_register(DND_FILES)
            self.dropzone.dnd_bind("<<Drop>>", self._on_drop)
            self.dropzone.dnd_bind("<<DragEnter>>", lambda e: self._drop_hover(True))
            self.dropzone.dnd_bind("<<DragLeave>>", lambda e: self._drop_hover(False))
        except Exception as e:
            print(f"拖拽不可用: {e}")

    def _drop_hover(self, on: bool):
        self.dropzone.configure(border_color=COLORS["text_2"] if on else COLORS["border_strong"])

    # ---------- 文件 ----------
    def _on_drop(self, event):
        import re
        paths = re.findall(r'\{([^}]+)\}|(\S+)', event.data)
        paths = [a or b for a, b in paths]
        added = 0
        for p in paths:
            path = Path(p)
            if path.is_file():
                self._add_file(path)
                added += 1
        if added:
            self._set_status(f"已添加 {added} 个文件")

    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="选择音视频文件",
            filetypes=[("音视频", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.mp3 *.aac *.m4a *.wav *.flac *.ogg *.ts *.m2ts"),
                       ("所有文件", "*.*")],
        )
        for p in paths:
            if p:
                self._add_file(Path(p))

    def _add_file(self, p: Path):
        if p in self.file_list:
            return
        self.file_list.append(p)
        self.file_presets[p] = self.default_preset_key
        if hasattr(self, "_empty_hint") and self._empty_hint:
            self._empty_hint.destroy()
            self._empty_hint = None
        size = p.stat().st_size
        size_s = f"{size/1024/1024:.1f} MB" if size > 1024*1024 else f"{size/1024:.0f} KB"
        ext = p.suffix.lstrip(".").upper()[:4]

        row = ctk.CTkFrame(self.file_list_frame, fg_color=COLORS["surface"], corner_radius=6)
        row.pack(fill="x", pady=2, padx=2)

        icon = ctk.CTkLabel(row, text=ext, width=44, height=24,
                            fg_color=COLORS["elevated"], corner_radius=4,
                            font=ctk.CTkFont(size=10, weight="bold"),
                            text_color=COLORS["text_2"])
        icon.pack(side="left", padx=(8, 8), pady=6)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(info, text=p.name, font=ctk.CTkFont(size=13),
                     text_color=COLORS["text"], anchor="w",
                     wraplength=220).pack(fill="x")
        ctk.CTkLabel(info, text=size_s, font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_3"], anchor="w").pack(fill="x")

        status = ctk.CTkLabel(row, text="待转码", font=ctk.CTkFont(size=11),
                              text_color=COLORS["text_3"], width=60)
        status.pack(side="right", padx=(4, 8))

        open_btn = ctk.CTkButton(
            row, text="打开", width=44, height=24,
            fg_color="transparent", border_width=1, border_color=COLORS["border"],
            hover_color=COLORS["hover"], text_color=COLORS["text_2"],
            font=ctk.CTkFont(size=10), corner_radius=4,
            state="disabled",
        )
        open_btn.pack(side="right", padx=(0, 4))

        preset_menu = ctk.CTkOptionMenu(
            row, values=PRESET_LABELS, width=140, height=26,
            font=ctk.CTkFont(size=11),
            fg_color=COLORS["elevated"], button_color=COLORS["border_strong"],
            button_hover_color=COLORS["hover"], text_color=COLORS["text_2"],
            dropdown_fg_color=COLORS["elevated"], dropdown_hover_color=COLORS["hover"],
            dropdown_text_color=COLORS["text"],
            command=lambda choice, path=p: self._on_row_preset(path, choice),
        )
        preset_menu.set(KEY_TO_LABEL[self.default_preset_key])
        preset_menu.pack(side="right", padx=(4, 8))

        # 删除按钮（✕）
        del_btn = ctk.CTkButton(
            row, text="✕", width=24, height=24,
            fg_color="transparent", hover_color="#3a1a1a",
            text_color=COLORS["text_3"],
            font=ctk.CTkFont(size=11), corner_radius=4,
            command=lambda path=p: self._remove_file(path),
        )
        del_btn.pack(side="right", padx=(0, 6))

        self.file_widgets[p] = {
            "row": row, "preset_menu": preset_menu,
            "status": status, "open_btn": open_btn, "del_btn": del_btn,
        }

    def _remove_file(self, path: Path):
        w = self.file_widgets.pop(path, {})
        if "row" in w:
            w["row"].destroy()
        if path in self.file_list:
            self.file_list.remove(path)
        self.file_presets.pop(path, None)
        self.file_outputs.pop(path, None)
        if not self.file_list:
            self._empty_hint = ctk.CTkLabel(
                self.file_list_frame, text="暂无文件",
                font=ctk.CTkFont(size=13), text_color=COLORS["text_3"],
            )
            self._empty_hint.pack(pady=30)
        self._set_status(f"已移除 {path.name}")

    # ---------- 预设 ----------
    def _on_default_preset(self, choice: str):
        self.default_preset_key = LABEL_TO_KEY[choice]

    def _on_row_preset(self, path: Path, choice: str):
        self.file_presets[path] = LABEL_TO_KEY[choice]

    def _apply_to_all(self):
        label = KEY_TO_LABEL[self.default_preset_key]
        for path in self.file_list:
            self.file_presets[path] = self.default_preset_key
            w = self.file_widgets.get(path, {})
            if "preset_menu" in w:
                w["preset_menu"].set(label)
        self._set_status(f"已将 {label} 应用到 {len(self.file_list)} 个文件")

    # ---------- 输出目录 ----------
    def _pick_output_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir = Path(d)
            self.output_dir_var.set(str(self.output_dir))

    def _open_output_dir(self):
        target = self.output_dir
        if not target:
            if self.file_list:
                target = self.file_list[0].parent / "transcoded"
            else:
                self._set_status("请先添加文件或选择输出目录")
                return
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))

    def _resolve_output_dir(self) -> Path:
        if self.output_dir:
            return self.output_dir
        return self.file_list[0].parent / "transcoded"

    # ---------- 队列 ----------
    def _set_status(self, s: str):
        self.msg_queue.put(("status", s))

    def _poll_queue(self):
        try:
            while True:
                kind, data = self.msg_queue.get_nowait()
                if kind == "status":
                    self.status_label.configure(text=data)
                elif kind == "progress":
                    self.progress.set(data / 100)
                elif kind == "row":
                    path, status_text = data
                    w = self.file_widgets.get(path, {})
                    if "status" in w:
                        w["status"].configure(text=status_text)
                    if "open_btn" in w and status_text == "✓ 完成":
                        w["open_btn"].configure(state="normal", command=lambda p=path: self._open_result(p))
                elif kind == "done":
                    self._on_done(data)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _open_result(self, path: Path):
        out = self.file_outputs.get(path)
        if out and out.is_file():
            os.startfile(str(out))

    # ---------- 执行 ----------
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.file_list:
            self._set_status("请先添加文件")
            return
        out_dir = self._resolve_output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        self.file_outputs.clear()

        self.cancel_flag.clear()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.set(0)
        self._set_status("准备中…")

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(list(self.file_list), out_dir),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, files: list[Path], out_dir: Path):
        try:
            ok = fail = 0
            total = len(files)
            for i, f in enumerate(files, 1):
                if self.cancel_flag.is_set():
                    self.msg_queue.put(("status", "已取消"))
                    break
                preset_key = self.file_presets.get(f, self.default_preset_key)
                preset = PRESETS[preset_key]
                out = out_dir / (f.stem + preset.ext)
                self.file_outputs[f] = out
                self.msg_queue.put(("status", f"[{i}/{total}] {f.name}"))
                self.msg_queue.put(("row", (f, "转码中…")))

                def cb(pr: Progress, idx=i):
                    if self.cancel_flag.is_set():
                        raise TranscodeError("已取消")
                    pct = ((idx - 1) + pr.percent / 100) / total * 100
                    self.msg_queue.put(("progress", pct))

                try:
                    self.engine.transcode(f, out, preset, overwrite=True, on_progress=cb)
                    ok += 1
                    self.msg_queue.put(("row", (f, "✓ 完成")))
                except Exception as e:
                    fail += 1
                    self.msg_queue.put(("row", (f, "✗ 失败")))
                    self.msg_queue.put(("status", f"失败: {e}"))
            self.msg_queue.put(("done", (ok, fail, total)))
        except Exception:
            self.msg_queue.put(("done", (0, 1, len(files))))

    def _cancel(self):
        self.cancel_flag.set()
        self._set_status("正在取消…")

    def _on_done(self, result):
        ok, fail, total = result
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self._set_status(f"完成：成功 {ok} / 失败 {fail} / 共 {total}")
        # 完成后弹提示，附打开目录按钮
        from tkinter import messagebox
        if ok > 0:
            if messagebox.askyesno("转码完成", f"成功 {ok} 个，失败 {fail} 个。\n是否打开输出文件夹？"):
                self._open_output_dir()


def main():
    app = TranscoderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
