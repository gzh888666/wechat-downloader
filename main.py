"""
微信视频号自动嗅探下载器 - 主程序
"""

import argparse
import atexit
import json
import os
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Optional
from queue import Queue, Empty

from core.proxy_manager import ProxyManager, check_certificate, ensure_certificate
from models.entities import VideoData
from utils.config import config
from utils.logger import logger

proxy_manager: Optional[ProxyManager] = None

_ipc_dir = Path(os.environ.get("TEMP", "/tmp")) / "wechat-downloader-ipc"


def cleanup_proxy():
    if proxy_manager:
        proxy_manager.cleanup()


def read_ipc_videos():
    results = []
    try:
        if _ipc_dir.exists():
            for f in _ipc_dir.glob("video_*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    results.append(data)
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass
    return results


def entry_to_video_data(entry):
    return VideoData(
        url=entry.get("url", ""),
        description=entry.get("description", ""),
        size=entry.get("size", 0),
        suffix=entry.get("suffix", ".mp4"),
        decode_key=entry.get("decode_key", ""),
        cover_url=entry.get("cover_url", ""),
        media_type=entry.get("media_type", "video"),
        formats=entry.get("formats", []),
    )


class AppUI:
    def __init__(self, save_dir: str, port: int):
        import tkinter as tk
        from tkinter import ttk

        self.process = None
        self.save_dir = save_dir
        self.video_items = []
        self.download_callbacks = {}
        self.download_queue = Queue()

        self.root = tk.Tk()
        self.root.title("风雪微信视频号下载器 v1.0.0      by: Snow")
        self.root.geometry("1110x740")
        self.root.minsize(800, 500)

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        tk.Label(
            top_frame, text="保存目录:", anchor="w", font=("Microsoft YaHei", 11)
        ).pack(side=tk.LEFT)

        self.save_dir_var = tk.StringVar(value=save_dir)
        self.save_dir_entry = tk.Entry(
            top_frame,
            textvariable=self.save_dir_var,
            font=("Microsoft YaHei", 11),
            width=50,
        )
        self.save_dir_entry.pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)
        self.save_dir_entry.bind("<Return>", lambda e: self._sync_save_dir())

        browse_btn = tk.Button(
            top_frame,
            text="浏览",
            command=self._browse_dir,
            width=6,
            font=("Microsoft YaHei", 10),
        )
        browse_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.sniff_all_var = tk.BooleanVar(value=False)
        sniff_all_cb = tk.Checkbutton(
            top_frame,
            text="嗅探全部",
            variable=self.sniff_all_var,
            command=self._on_sniff_all_changed,
            font=("Microsoft YaHei", 11),
        )
        sniff_all_cb.pack(side=tk.LEFT, padx=(10, 0))

        fix_btn = tk.Button(
            top_frame,
            text="修复网络",
            command=self._fix_network,
            width=10,
            bg="#f39c12",
            fg="white",
            font=("Microsoft YaHei", 11, "bold"),
        )
        fix_btn.pack(side=tk.RIGHT, padx=(10, 0))

        clear_btn = tk.Button(
            top_frame,
            text="清空",
            command=self._clear_list,
            width=8,
            font=("Microsoft YaHei", 11),
        )
        clear_btn.pack(side=tk.RIGHT, padx=(5, 0))

        columns = ("title", "size", "status")
        self.tree = ttk.Treeview(
            self.root, columns=columns, show="headings", selectmode="browse", height=20
        )
        self.tree.heading("title", text="视频标题（捕获中...）")
        self.tree.heading("size", text="大小")
        self.tree.heading("status", text="操作")
        self.tree.column("title", width=680, anchor="w")
        self.tree.column("size", width=120, anchor="center")
        self.tree.column("status", width=150, anchor="center")

        self.status_var = tk.StringVar(value="⏳ 初始化中...")
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 10))
        status_bar = tk.Label(
            bottom_frame,
            textvariable=self.status_var,
            anchor="w",
            relief=tk.SUNKEN,
            fg="gray",
            font=("Microsoft YaHei", 11),
        )
        status_bar.pack(fill=tk.X, ipady=3)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        style = ttk.Style()
        style.configure("Treeview", font=("Microsoft YaHei", 12), rowheight=40)
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 13, "bold"))
        style.configure(
            "download.Treeview",
            foreground="#2980b9",
            font=("Microsoft YaHei", 12, "bold"),
        )
        style.configure(
            "downloading.Treeview", foreground="#e67e22", font=("Microsoft YaHei", 12)
        )
        style.configure(
            "done.Treeview", foreground="#27ae60", font=("Microsoft YaHei", 12)
        )
        style.configure(
            "failed.Treeview", foreground="#e74c3c", font=("Microsoft YaHei", 12)
        )

        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.bind("<Double-1>", self._on_double_click)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def add_video(self, video_data):
        from downloaders.video_downloader import format_size

        desc = video_data.display_name
        size_str = format_size(video_data.size) if video_data.size else "-"
        encrypt_tag = " 🔐" if video_data.is_encrypted else ""

        item_id = self.tree.insert(
            "",
            "end",
            values=(desc + encrypt_tag, size_str, "⬇ 解密下载"),
            tags=("download",),
        )
        self.video_items.append(item_id)
        self.download_callbacks[item_id] = video_data

        count = len(self.video_items)
        self.tree.heading("title", text=f"视频标题（已捕获 {count} 个）")
        self.status_var.set(f"已嗅探到 {count} 个视频")

    def mark_downloading(self, item_id):
        try:
            vals = self.tree.item(item_id, "values")
            self.tree.item(
                item_id,
                values=(vals[0], vals[1], "⏳ 下载中..."),
                tags=("downloading",),
            )
        except Exception:
            pass

    def mark_done(self, item_id):
        try:
            vals = self.tree.item(item_id, "values")
            self.tree.item(
                item_id, values=(vals[0], vals[1], "✅ 已完成"), tags=("done",)
            )
        except Exception:
            pass

    def mark_failed(self, item_id):
        try:
            vals = self.tree.item(item_id, "values")
            self.tree.item(
                item_id, values=(vals[0], vals[1], "❌ 失败"), tags=("failed",)
            )
        except Exception:
            pass

    def _on_double_click(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        item_id = selection[0]
        self._download_item(item_id)

    def _sync_save_dir(self):
        try:
            path = Path(self.save_dir_var.get().strip()).absolute()
            path.mkdir(parents=True, exist_ok=True)
            self.save_dir = str(path)
            return True
        except Exception as e:
            self.status_var.set(f"❌ 目录无效: {e}")
            logger.error(f"保存目录无效: {e}")
            return False

    def _download_item(self, item_id):
        if item_id not in self.download_callbacks:
            return
        vals = self.tree.item(item_id, "values")
        if vals[2] != "⬇ 解密下载":
            return

        if not self._sync_save_dir():
            return

        video_data = self.download_callbacks[item_id]
        self.mark_downloading(item_id)
        self.download_queue.put((video_data, item_id))

    def _on_sniff_all_changed(self):
        try:
            _ipc_dir.mkdir(parents=True, exist_ok=True)
            flag_file = _ipc_dir / "sniff_all.json"
            with open(flag_file, "w", encoding="utf-8") as f:
                json.dump({"sniff_all": self.sniff_all_var.get()}, f)
        except Exception as e:
            logger.error(f"写入嗅探模式失败: {e}")

    def _browse_dir(self):
        from tkinter import filedialog

        selected = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if selected:
            self.save_dir_var.set(selected)
            self.save_dir = selected
            os.makedirs(selected, exist_ok=True)

    def _clear_list(self):
        for item_id in self.video_items:
            self.tree.delete(item_id)
        self.video_items.clear()
        self.download_callbacks.clear()
        self.tree.heading("title", text="视频标题（捕获中...）")
        self.status_var.set("列表已清空")

    def _fix_network(self):
        import platform

        system = platform.system().lower()

        if system == "windows":
            try:
                import winreg
                import ctypes

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                    0,
                    winreg.KEY_ALL_ACCESS,
                )
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                winreg.CloseKey(key)

                ctypes.windll.Wininet.InternetSetOptionW(0, 39, 0, 0)
                ctypes.windll.Wininet.InternetSetOptionW(0, 37, 0, 0)

                self.status_var.set("✅ 已关闭系统代理，网络已恢复")
                logger.success("✅修复网络: 已关闭系统代理")
            except Exception as e:
                self.status_var.set(f"❌ 修复失败: {e}")
                logger.error(f"修复网络失败: {e}")

        elif system == "darwin":
            try:
                from core.proxy_manager import ProxyManager

                ProxyManager._cleanup_macos()
                self.status_var.set("✅ 已清理 macOS 代理，网络已恢复")
            except Exception as e:
                self.status_var.set(f"❌ 修复失败: {e}")
                logger.error(f"修复网络失败: {e}")
        else:
            self.status_var.set("请手动关闭系统代理设置")

    def _on_close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        cleanup_proxy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def do_download(video_data, item_id, app):
    from downloaders.video_downloader import generate_filename, VideoDownloader
    from downloaders.m3u8_downloader import M3U8Downloader, is_m3u8_url
    from crypto.decryptor import decrypt_wechat_video
    from models.exceptions import DecryptError, DownloadError

    url = video_data.url
    filename = generate_filename(
        video_data.description, video_data.url, video_data.suffix
    )
    filepath = Path(os.path.join(app.save_dir, filename))

    counter = 1
    while filepath.exists():
        filepath = Path(
            os.path.join(
                app.save_dir,
                f"{filepath.stem}_{counter}{video_data.suffix}",
            )
        )
        counter += 1

    logger.info(f"⬇️{filepath.name} 下载中...")

    if is_m3u8_url(url):
        downloader = M3U8Downloader(m3u8_url=url, save_path=str(filepath), headers={})
        success = downloader.download()
    else:
        downloader = VideoDownloader(
            url=url,
            save_path=str(filepath),
            thread_count=4,
        )
        success = downloader.start()

    try:
        if success:
            actual_file = filepath
            if hasattr(downloader, "save_path"):
                actual_file = Path(downloader.save_path)

            if video_data.is_encrypted:
                logger.info(f"🔓{actual_file.name} 解密中...")
                if decrypt_wechat_video(str(actual_file), video_data.decode_key):
                    logger.success(f"✅{actual_file.name} 下载完成")
                    try:
                        app.root.after(0, lambda: app.mark_done(item_id))
                    except Exception:
                        pass
                else:
                    raise DecryptError(f"解密失败: {actual_file.name}")
            else:
                logger.success(f"✅{actual_file.name} 下载完成")
                try:
                    app.root.after(0, lambda: app.mark_done(item_id))
                except Exception:
                    pass
        else:
            temp_file = str(filepath) + ".tmp"
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise DownloadError(f"{url} 视频下载失败")
    except (DecryptError, DownloadError) as e:
        logger.error(e)
        try:
            app.root.after(0, lambda: app.mark_failed(item_id))
        except Exception:
            pass
    except Exception as e:
        logger.error(str(e), exc_info=True)
        try:
            app.root.after(0, lambda: app.mark_failed(item_id))
        except Exception:
            pass


def main():
    global proxy_manager

    parser = argparse.ArgumentParser(
        description="微信视频号自动嗅探下载器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-d",
        "--dir",
        default=config.download_dir,
        help=f"视频保存目录 (默认: {config.download_dir})",
    )

    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=config.proxy_port,
        help=f"代理服务器端口 (默认: {config.proxy_port})",
    )

    parser.add_argument(
        "--no-auto-proxy", action="store_true", help="不自动设置系统代理"
    )

    args = parser.parse_args()

    if args.dir == config.download_dir:
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.shell32.SHGetFolderPathW(0, 14, 0, 0, buf)
            save_dir = Path(buf.value) / "WeChatDownloader"
        except Exception:
            save_dir = Path(config.download_dir)
    else:
        save_dir = Path(args.dir).absolute()
    save_dir.mkdir(parents=True, exist_ok=True)
    port = args.port

    app = AppUI(str(save_dir), port)
    app.status_var.set("⏳ 初始化中...")

    def do_init():
        global proxy_manager

        logger.info("")
        logger.info("=" * 70)
        logger.info("  🎬微信视频号自动嗅探下载器")
        logger.info(f"  📁保存目录: {save_dir}")
        logger.info(f"  🌐代理端口: {port}")
        logger.info("=" * 70)
        logger.info("")

        try:
            app.root.after(0, lambda: app.status_var.set("⏳ 清理端口占用..."))
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=0x08000000,
            )
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTEN" in line:
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit():
                            logger.warning(
                                f"⚠️端口 {port} 被进程 {pid} 占用，正在清理..."
                            )
                            subprocess.run(
                                ["taskkill", "/PID", pid, "/F"],
                                capture_output=True,
                                creationflags=0x08000000,
                            )
                            time.sleep(0.5)
                            logger.success(f"✅已清理占用端口的进程 {pid}")
        except Exception:
            pass

        env = os.environ.copy()
        env["SAVE_DIR"] = str(save_dir)
        env["PORT"] = str(port)

        import shutil

        mitmdump_path = shutil.which("mitmdump")
        if not mitmdump_path:
            venv_mitmdump = Path(sys.executable).parent / "mitmdump.exe"
            if venv_mitmdump.exists():
                mitmdump_path = str(venv_mitmdump)
            else:
                local_mitmdump = (
                    Path(sys.executable).parent / "Scripts" / "mitmdump.exe"
                )
                if local_mitmdump.exists():
                    mitmdump_path = str(local_mitmdump)
        if not mitmdump_path:
            exe_dir = Path(sys.executable).parent
            for candidate in [
                exe_dir / ".venv" / "Scripts" / "mitmdump.exe",
                exe_dir.parent / ".venv" / "Scripts" / "mitmdump.exe",
                Path.cwd() / ".venv" / "Scripts" / "mitmdump.exe",
            ]:
                if candidate.exists():
                    mitmdump_path = str(candidate)
                    break
        if not mitmdump_path:
            mitmdump_path = "mitmdump"

        addon_script = Path(__file__).parent / "core" / "addon_server.py"
        if not addon_script.exists():
            addon_script = Path(sys.executable).parent / "core" / "addon_server.py"
        if not addon_script.exists():
            addon_script = Path.cwd() / "core" / "addon_server.py"

        cmd = [
            mitmdump_path,
            "-s",
            str(addon_script),
            "-p",
            str(port),
            "--set",
            "block_global=false",
            "--set",
            "stream_large_bodies=5m",
            "--ssl-insecure",
            "--quiet",
        ]

        try:
            app.root.after(0, lambda: app.status_var.set("⏳ 启动代理服务器..."))
            logger.info("🚀启动代理服务器...")
            process = subprocess.Popen(cmd, env=env, creationflags=0x08000000)
            app.process = process

            time.sleep(1)

            app.root.after(0, lambda: app.status_var.set("⏳ 检查证书..."))
            if not check_certificate():
                logger.warning("⚠️无法连接到代理，可能需要安装证书")

            from core.proxy_manager import is_cert_trusted

            if not is_cert_trusted():
                app.root.after(0, lambda: app.status_var.set("⏳ 等待证书安装..."))
                logger.warning("⚠️mitmproxy 证书未安装到系统信任存储")
                logger.info("   证书未安装时设置系统代理会导致断网，请先安装证书")
                ensure_certificate()
                logger.info("")
                logger.info("⏳等待证书安装完成...")
                for i in range(30):
                    time.sleep(1)
                    if is_cert_trusted():
                        logger.success("✅检测到证书已安装到系统信任存储")
                        break
                else:
                    logger.warning("⚠️等待超时，请确认证书已正确安装")
                    logger.info("   如果已安装，请重新运行程序")

            if not args.no_auto_proxy:
                app.root.after(0, lambda: app.status_var.set("⏳ 设置系统代理..."))
                proxy_manager = ProxyManager("127.0.0.1", port)

                if proxy_manager.setup():
                    atexit.register(cleanup_proxy)
                else:
                    logger.warning("⚠️自动设置代理失败，请手动设置")
                    logger.warning(f"代理地址: 127.0.0.1:{port}")
                    proxy_manager = None
            else:
                logger.info(f"⚠️请手动设置系统代理: 127.0.0.1:{port}")

            _ipc_dir.mkdir(exist_ok=True)

            app.root.after(
                0, lambda: app.status_var.set("就绪 - 打开微信访问视频号即可嗅探视频")
            )

            seen_urls = set()

            def poll_ipc():
                while True:
                    if process.poll() is not None:
                        try:
                            app.root.destroy()
                        except Exception:
                            pass
                        break

                    entries = read_ipc_videos()
                    for entry in entries:
                        url = entry.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            video_data = entry_to_video_data(entry)
                            logger.info(
                                f"[UI] 新视频加入列表: {video_data.display_name[:40]}"
                            )
                            try:
                                app.root.after(
                                    0, lambda vd=video_data: app.add_video(vd)
                                )
                            except Exception:
                                pass

                    time.sleep(0.5)

            threading.Thread(target=poll_ipc, daemon=True).start()

            def poll_download():
                while True:
                    try:
                        video_data, item_id = app.download_queue.get(timeout=0.5)
                    except Empty:
                        if process.poll() is not None:
                            break
                        continue
                    do_download(video_data, item_id, app)

            threading.Thread(target=poll_download, daemon=True).start()

        except FileNotFoundError:
            logger.error("❌找不到 mitmdump 命令")
            app.root.after(0, lambda: app.status_var.set("❌ 找不到 mitmdump 命令"))

        except Exception as e:
            logger.error(f"❌错误: {e}")
            app.root.after(0, lambda: app.status_var.set(f"❌ 初始化失败: {e}"))

    threading.Thread(target=do_init, daemon=True).start()
    app.run()
    cleanup_proxy()


if __name__ == "__main__":
    main()
