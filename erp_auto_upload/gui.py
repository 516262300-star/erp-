from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from main import bundle_to_dict
from parser.folder_parser import parse_material_folder


APP_TITLE = "ERP 自动上架工具"


class UploadGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x680")
        self.minsize(780, 560)

        self.material_root = tk.StringVar()
        self.status = tk.StringVar(value="请选择本次商品素材文件夹")
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.after(200, self._drain_output)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        path_frame = ttk.LabelFrame(outer, text="商品素材文件夹")
        path_frame.pack(fill=tk.X)
        path_frame.columnconfigure(0, weight=1)

        path_entry = ttk.Entry(path_frame, textvariable=self.material_root)
        path_entry.grid(row=0, column=0, padx=(10, 8), pady=10, sticky="ew")
        ttk.Button(path_frame, text="选择文件夹", command=self.choose_folder).grid(row=0, column=1, padx=(0, 10), pady=10)

        button_frame = ttk.Frame(outer)
        button_frame.pack(fill=tk.X, pady=(12, 8))

        self.parse_button = ttk.Button(button_frame, text="解析检查", command=self.parse_current_folder)
        self.parse_button.pack(side=tk.LEFT)
        self.precheck_button = ttk.Button(button_frame, text="ERP核对", command=self.start_precheck)
        self.precheck_button.pack(side=tk.LEFT, padx=(8, 0))
        self.upload_button = ttk.Button(button_frame, text="开始上架（不保存）", command=self.start_upload)
        self.upload_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_button = ttk.Button(button_frame, text="停止脚本", command=self.stop_upload, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(button_frame, textvariable=self.status).pack(side=tk.LEFT, padx=(16, 0))

        summary_frame = ttk.LabelFrame(outer, text="解析结果")
        summary_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 8))

        self.summary_text = tk.Text(summary_frame, height=16, wrap=tk.NONE)
        summary_y = ttk.Scrollbar(summary_frame, orient=tk.VERTICAL, command=self.summary_text.yview)
        summary_x = ttk.Scrollbar(summary_frame, orient=tk.HORIZONTAL, command=self.summary_text.xview)
        self.summary_text.configure(yscrollcommand=summary_y.set, xscrollcommand=summary_x.set)
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        summary_y.grid(row=0, column=1, sticky="ns")
        summary_x.grid(row=1, column=0, sticky="ew")
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(outer, text="运行日志")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
        log_y = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_y.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_y.grid(row=0, column=1, sticky="ns")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择本次商品素材文件夹")
        if folder:
            self.material_root.set(folder)
            self.parse_current_folder()

    def parse_current_folder(self) -> None:
        path = self._get_material_path()
        if path is None:
            return
        try:
            bundle = parse_material_folder(path)
        except Exception as exc:
            self.status.set("解析失败")
            messagebox.showerror(APP_TITLE, str(exc))
            return

        payload = bundle_to_dict(bundle)
        video_summary = payload["video"] or "未匹配，跳过"
        if payload["video_size_mb"] is not None:
            video_summary = f"{video_summary}（{payload['video_size_mb']} MB）"

        lines = [
            f"链接标题：{payload['link_title']}",
            f"主图：{len(payload['main_images'])} 张",
            f"详情图：{len(payload['detail_images'])} 张",
            f"尺寸图 / SKU：{len(payload['size_images'])} 张",
            f"无色图：{len(payload['no_color_images'])} 张",
            f"视频：{video_summary}",
            "",
            "SKU 列表：",
        ]
        for index, sku in enumerate(payload["skus"], start=1):
            lines.append(
                f"{index:02d}. {sku['source_stem']} -> 型号 {sku['erp_model']} / 颜色 {sku['erp_color']} / 外显 {sku['display_name']}"
            )
        self._set_summary("\n".join(lines))
        self.status.set("解析完成，可以开始上架")

    def start_upload(self) -> None:
        self._start_script("upload", "开始上架：直接填写上传；只有型号没有精确候选时才用 ERP 唯一候选兜底。\n")

    def start_precheck(self) -> None:
        self._start_script("precheck", "开始 ERP 核对：只核对型号、颜色和成本，不填写、不上传。\n", extra_args=["--no-pause"])

    def _start_script(self, command: str, log_message: str, extra_args: list[str] | None = None) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning(APP_TITLE, "已有脚本正在运行")
            return
        path = self._get_material_path()
        if path is None:
            return
        try:
            parse_material_folder(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        self._append_log(log_message)
        script = Path(__file__).with_name("main.py")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        args = [sys.executable, str(script), command, "--material-root", str(path), *(extra_args or [])]
        self.process = subprocess.Popen(
            args,
            cwd=str(Path(__file__).parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        self.status.set("脚本运行中")
        self._set_running(True)
        threading.Thread(target=self._read_process_output, daemon=True).start()

    def stop_upload(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        if not messagebox.askyesno(APP_TITLE, "确定停止当前上架脚本并关闭自动化浏览器吗？"):
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.status.set("已停止")
        self._set_running(False)

    def _read_process_output(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self.output_queue.put(line)
        return_code = self.process.wait()
        self.output_queue.put(f"\n脚本已结束，退出码：{return_code}\n")
        self.output_queue.put("__PROCESS_DONE__")

    def _drain_output(self) -> None:
        while True:
            try:
                item = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__PROCESS_DONE__":
                self.status.set("脚本已结束")
                self._set_running(False)
            else:
                self._append_log(item)
        self.after(200, self._drain_output)

    def _get_material_path(self) -> Path | None:
        raw_path = self.material_root.get().strip().strip('"')
        if not raw_path:
            messagebox.showwarning(APP_TITLE, "请先填写或选择商品素材文件夹")
            return None
        return Path(raw_path)

    def _set_summary(self, text: str) -> None:
        self.summary_text.configure(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, text)
        self.summary_text.configure(state=tk.DISABLED)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        self.upload_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.precheck_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.parse_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_button.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(APP_TITLE, "上架脚本还在运行，关闭软件会停止脚本。确定关闭吗？"):
                return
            self.stop_upload()
        self.destroy()


def main() -> None:
    app = UploadGui()
    app.mainloop()


if __name__ == "__main__":
    main()
