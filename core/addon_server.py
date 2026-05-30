"""
mitmproxy 插件服务器
这个文件会被 mitmdump 加载
"""

import json
import os
import time
from pathlib import Path

from core.proxy_addon import WechatVideoAddon, extract_video_url, extract_all_video_urls
from utils.logger import logger

_ipc_dir = Path(os.environ.get("TEMP", "/tmp")) / "wechat-downloader-ipc"
_ipc_dir.mkdir(parents=True, exist_ok=True)

_ipc_counter = 0
downloaded_urls = set()
_seen_descriptions = set()


def _read_sniff_all():
    try:
        flag_file = _ipc_dir / "sniff_all.json"
        if flag_file.exists():
            with open(flag_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("sniff_all", False)
    except Exception:
        pass
    return False


def _write_ipc(entry):
    global _ipc_counter
    try:
        _ipc_dir.mkdir(parents=True, exist_ok=True)
        _ipc_counter += 1
        ipc_file = _ipc_dir / f"video_{_ipc_counter}_{int(time.time() * 1000)}.json"
        with open(ipc_file, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"IPC写入失败: {e}")


def _video_data_to_entry(video_data):
    return {
        "url": video_data.url,
        "description": video_data.description,
        "size": video_data.size,
        "suffix": video_data.suffix,
        "decode_key": video_data.decode_key,
        "cover_url": video_data.cover_url,
        "media_type": video_data.media_type,
        "formats": video_data.formats,
        "timestamp": time.time(),
    }


def on_video_found(video_info: dict, source_url: str = "") -> None:
    """视频发现回调 - 写入IPC文件供主进程读取"""
    global _ipc_counter

    sniff_all = _read_sniff_all()
    media_count = len(video_info.get("media", []))
    desc = video_info.get("description", "")[:30]
    logger.info(
        f"[嗅探回调] 收到视频信息: description={desc}, media数量={media_count}, sniff_all={sniff_all}"
    )

    if sniff_all:
        video_list = extract_all_video_urls(video_info)
        if not video_list:
            return
        for video_data in video_list:
            url = video_data.url
            if url in downloaded_urls:
                continue
            downloaded_urls.add(url)
            logger.info(
                f"[嗅探回调] 提取视频(全部模式): {video_data.display_name[:40]}"
            )
            _write_ipc(_video_data_to_entry(video_data))
    else:
        video_data = extract_video_url(video_info)
        if not video_data:
            return
        url = video_data.url
        if url in downloaded_urls:
            return

        video_desc = video_data.description
        if video_desc in _seen_descriptions:
            logger.info(
                f"[嗅探回调] 单个模式下忽略重复description: {video_data.display_name[:40]}"
            )
            return

        downloaded_urls.add(url)
        _seen_descriptions.add(video_desc)
        logger.info(f"[嗅探回调] 提取视频(单个模式): {video_data.display_name[:40]}")
        _write_ipc(_video_data_to_entry(video_data))


addon_instance = WechatVideoAddon(video_callback=on_video_found, version="1.0.0")

addons = [addon_instance]
