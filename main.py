"""
微信视频号自动嗅探下载器 - 主程序
"""

import argparse
import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from core.proxy_manager import ProxyManager, check_certificate, ensure_certificate
from utils.config import config
from utils.logger import logger

proxy_manager: Optional[ProxyManager] = None


def cleanup_proxy():
    """清理代理（在程序退出时自动调用）"""
    if proxy_manager:
        proxy_manager.cleanup()


def main():
    """主函数"""
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

    save_dir = Path(args.dir).absolute()
    save_dir.mkdir(exist_ok=True)
    port = args.port

    logger.info("")
    logger.info("=" * 70)
    logger.info("  🎬微信视频号自动嗅探下载器")
    logger.info(f"  📁保存目录: {save_dir}")
    logger.info(f"  🌐代理端口: {port}")
    logger.info("=" * 70)
    logger.info("")

    env = os.environ.copy()
    env["SAVE_DIR"] = str(save_dir)
    env["PORT"] = str(port)

    addon_script = Path(__file__).parent / "core" / "addon_server.py"

    cmd = [
        "mitmdump",
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

    process = None

    try:
        logger.info("🚀启动代理服务器...")
        process = subprocess.Popen(cmd, env=env)

        time.sleep(1)

        if not check_certificate():
            logger.warning("⚠️无法连接到代理，可能需要安装证书")

        from core.proxy_manager import is_cert_trusted

        if not is_cert_trusted():
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
            proxy_manager = ProxyManager("127.0.0.1", port)

            if proxy_manager.setup():
                atexit.register(cleanup_proxy)
            else:
                logger.warning("⚠️自动设置代理失败，请手动设置")
                logger.warning(f"代理地址: 127.0.0.1:{port}")
                proxy_manager = None
        else:
            logger.info(f"⚠️请手动设置系统代理: 127.0.0.1:{port}")

        logger.info("")
        logger.info("📌使用提示:")
        logger.info("   1. 关闭微信后重新打开")
        logger.info("   2. 访问视频号页面，程序将自动嗅探并下载视频")
        logger.info("   3. 按 Ctrl+C 停止程序")
        logger.info("")

        process.wait()

    except KeyboardInterrupt:
        logger.info("⏸️️正在停止...")
        if process:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        logger.success("✅已停止")

    except FileNotFoundError:
        logger.error("❌找不到 mitmdump 命令")
        sys.exit(1)

    except Exception as e:
        logger.error(f"❌错误: {e}")
        sys.exit(1)

    finally:
        cleanup_proxy()


if __name__ == "__main__":
    main()
