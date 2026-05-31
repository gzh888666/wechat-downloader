"""
系统代理管理器
自动设置和清理系统代理
"""

import os
import platform
import subprocess

from utils.logger import logger


class ProxyManager:
    """系统代理管理"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8899):
        self.host = host
        self.port = port
        self.system = platform.system()
        self.network_service = None

    def setup(self) -> bool:
        """设置系统代理"""
        try:
            if self.system.lower() == "darwin":
                return self._setup_macos()
            elif self.system.lower() == "windows":
                return self._setup_windows()
            elif self.system.lower() == "linux":
                return self._setup_linux()
            else:
                logger.error(f"不支持的系统: {self.system}")
                return False
        except Exception as e:
            logger.error(f"设置代理失败: {e}")
            return False

    def cleanup(self) -> bool:
        """清理系统代理"""
        try:
            if self.system.lower() == "darwin":
                return self._cleanup_macos()
            elif self.system.lower() == "windows":
                return self._cleanup_windows()
            elif self.system.lower() == "linux":
                return self._cleanup_linux()
            return True
        except Exception as e:
            logger.error(f"清理代理失败: {e}")
            return False

    @staticmethod
    def _get_all_macos_network_services() -> list:
        """获取 macOS 所有有效的网络服务"""
        try:
            common_services = [
                "USB 10/100 LAN",
                "Wi-Fi",
                "Ethernet",
                "以太网",
                "Thunderbolt Bridge",
            ]
            available_services = []

            for service in common_services:
                result = subprocess.run(
                    ["networksetup", "-getwebproxy", service],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    available_services.append(service)

            result = subprocess.run(
                ["networksetup", "-listallnetworkservices"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines[1:]:
                    service = line.strip()
                    if service and service not in available_services:
                        result = subprocess.run(
                            ["networksetup", "-getwebproxy", service],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode == 0:
                            available_services.append(service)

            return available_services if available_services else ["Wi-Fi"]
        except:
            return ["Wi-Fi"]

    def _setup_macos(self) -> bool:
        """设置 macOS 代理"""
        services = self._get_all_macos_network_services()
        success = False

        for service in services:
            commands = [
                ["networksetup", "-setwebproxy", service, self.host, str(self.port)],
                [
                    "networksetup",
                    "-setsecurewebproxy",
                    service,
                    self.host,
                    str(self.port),
                ],
                ["networksetup", "-setwebproxystate", service, "on"],
                ["networksetup", "-setsecurewebproxystate", service, "on"],
            ]

            for cmd in commands:
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode != 0:
                    logger.warning(f"命令失败: {' '.join(cmd)}")
                success = success or result.returncode == 0

            logger.success(f"✅已设置代理 ({service}): {self.host}:{self.port}")

        self.network_service = services[0] if services else "Wi-Fi"
        return success

    def _cleanup_macos(self) -> bool:
        """清理 macOS 代理"""
        services = self._get_all_macos_network_services()

        for service in services:
            commands = [
                ["networksetup", "-setwebproxystate", service, "off"],
                ["networksetup", "-setsecurewebproxystate", service, "off"],
            ]

            for cmd in commands:
                subprocess.run(cmd, capture_output=True)

            logger.success(f"✅已清理代理 ({service})")

        return True

    def _setup_windows(self) -> bool:
        """设置 Windows 代理"""
        try:
            import winreg

            internet_settings = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_ALL_ACCESS,
            )

            winreg.SetValueEx(internet_settings, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(
                internet_settings,
                "ProxyServer",
                0,
                winreg.REG_SZ,
                f"{self.host}:{self.port}",
            )

            winreg.CloseKey(internet_settings)

            import ctypes

            internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
            internet_set_option(0, 39, 0, 0)
            internet_set_option(0, 37, 0, 0)

            logger.success(f"✅已设置系统代理: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"设置 Windows 代理失败: {e}")
            return False

    @staticmethod
    def _cleanup_windows() -> bool:
        """清理 Windows 代理"""
        try:
            import winreg

            internet_settings = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_ALL_ACCESS,
            )

            winreg.SetValueEx(internet_settings, "ProxyEnable", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(internet_settings)

            import ctypes

            internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
            internet_set_option(0, 39, 0, 0)
            internet_set_option(0, 37, 0, 0)

            logger.success("✅已清理系统代理")
            return True
        except Exception as e:
            logger.error(f"清理 Windows 代理失败: {e}")
            return False

    def _setup_linux(self) -> bool:
        """设置 Linux 代理（通过环境变量）"""
        logger.info(f"请手动设置代理: {self.host}:{self.port}")
        return True

    @staticmethod
    def _cleanup_linux() -> bool:
        """清理 Linux 代理"""
        logger.info("请手动清理代理设置")
        return True


def check_certificate() -> bool:
    """检查 mitmproxy 证书是否已安装"""
    import urllib3
    import requests

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        response = requests.get("http://mitm.it", timeout=3, verify=False)
        if response.status_code == 200:
            logger.success("✅mitmproxy 代理运行正常")

            import os
            from pathlib import Path

            home = Path.home()
            cert_paths = [
                home / ".mitmproxy" / "mitmproxy-ca-cert.pem",
                home / ".mitmproxy" / "mitmproxy-ca-cert.p12",
            ]

            cert_exists = any(p.exists() for p in cert_paths)
            if cert_exists:
                logger.success("✅检测到 mitmproxy 证书文件")
            else:
                logger.warning("⚠️未检测到证书文件")

            return True
    except:
        pass

    return False


def is_cert_trusted() -> bool:
    """检查 mitmproxy 证书是否已安装到系统信任存储"""
    import platform

    system = platform.system().lower()

    if system == "windows":
        try:
            import subprocess

            result = subprocess.run(
                ["certutil", "-store", "-enterprise", "Root"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=0x08000000,
            )
            if "mitmproxy" in result.stdout:
                return True
            result = subprocess.run(
                ["certutil", "-store", "Root"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=0x08000000,
            )
            if "mitmproxy" in result.stdout:
                return True
        except Exception:
            pass
    elif system == "darwin":
        try:
            import subprocess

            result = subprocess.run(
                [
                    "security",
                    "find-certificate",
                    "-c",
                    "mitmproxy",
                    "-p",
                    "/Library/Keychains/System.keychain",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


def ensure_certificate() -> None:
    """确保证书已安装，未安装则自动下载并打开"""
    from pathlib import Path

    if is_cert_trusted():
        logger.success("✅mitmproxy 证书已安装到系统信任存储")
        return

    logger.warning("⚠️mitmproxy 证书未安装到系统信任存储，正在自动安装...")

    home = Path.home()
    cert_dir = home / ".mitmproxy"
    cert_dir.mkdir(exist_ok=True)

    system = platform.system().lower()

    if system == "windows":
        p12_path = cert_dir / "mitmproxy-ca-cert.p12"

        if not p12_path.exists():
            logger.info("📥正在从 mitm.it 下载证书...")
            try:
                import urllib3
                import requests

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                resp = requests.get(
                    "http://mitm.it/cert/cert.p12", timeout=10, verify=False
                )
                if resp.status_code == 200:
                    p12_path.write_bytes(resp.content)
                    logger.success(f"✅证书已下载: {p12_path}")
                else:
                    logger.error(f"❌证书下载失败 (HTTP {resp.status_code})")
                    return
            except Exception as e:
                logger.error(f"❌证书下载失败: {e}")
                return

        logger.info("📂正在打开证书，请在弹出的窗口中完成安装:")
        logger.info("   1. 点击'安装证书'")
        logger.info("   2. 存储位置选'本地计算机' → 下一步")
        logger.info(
            "   3. 选择'将所有证书放入下列存储' → 浏览 → '受信任的根证书颁发机构'"
        )
        logger.info("   4. 点击'下一步' → '完成'")

        try:
            os.startfile(str(p12_path))
        except Exception as e:
            logger.error(f"❌无法自动打开证书: {e}")
            logger.info(f"   请手动双击证书文件: {p12_path}")

    elif system == "darwin":
        pem_path = cert_dir / "mitmproxy-ca-cert.pem"

        if not pem_path.exists():
            logger.info("📥正在从 mitm.it 下载证书...")
            try:
                import urllib3
                import requests

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                resp = requests.get(
                    "http://mitm.it/cert/cert.pem", timeout=10, verify=False
                )
                if resp.status_code == 200:
                    pem_path.write_bytes(resp.content)
                    logger.success(f"✅证书已下载: {pem_path}")
                else:
                    logger.error(f"❌证书下载失败 (HTTP {resp.status_code})")
                    return
            except Exception as e:
                logger.error(f"❌证书下载失败: {e}")
                return

        logger.info("📂正在打开钥匙串访问，请将 mitmproxy 证书设为'始终信任'")
        try:
            subprocess.Popen(["open", "-a", "Keychain Access", str(pem_path)])
        except Exception as e:
            logger.error(f"❌无法自动打开证书: {e}")
            logger.info(f"   请手动双击证书文件: {pem_path}")

    else:
        logger.info("请手动安装 mitmproxy 证书")
        logger.info(f"   证书目录: {cert_dir}")
