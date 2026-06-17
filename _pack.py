"""打包辅助脚本"""

import zipfile
import os
import shutil
import subprocess
import sys

base = os.path.dirname(os.path.abspath(__file__))

venv_python = os.path.join(base, ".venv", "Scripts", "python.exe")
if not os.path.exists(venv_python):
    venv_python = os.path.join(base, ".venv", "bin", "python")
if not os.path.exists(venv_python):
    venv_python = sys.executable

print(f"使用 Python: {venv_python}")

print("[1/5] 清理旧文件...")
for d in ["build", "dist"]:
    p = os.path.join(base, d)
    if os.path.exists(p):
        shutil.rmtree(p)
for f in ["WxDown.spec"]:
    p = os.path.join(base, f)
    if os.path.exists(p):
        os.remove(p)
print("清理完成")

print("\n[2/5] PyInstaller 打包...")
subprocess.run(
    [
        venv_python,
        "-m",
        "PyInstaller",
        "--windowed",
        "--name",
        "WxDown",
        "--icon",
        "WxDown.ico",
        "--add-data",
        "core;core",
        "--add-data",
        "crypto;crypto",
        "--add-data",
        "downloaders;downloaders",
        "--add-data",
        "models;models",
        "--add-data",
        "utils;utils",
        "main.py",
    ],
    cwd=base,
    check=True,
)
print("打包完成")

print("\n[3/5] 复制 .venv 到 dist/WxDown...")
venv_src = os.path.join(base, ".venv")
venv_dst = os.path.join(base, "dist", "WxDown", ".venv")
if os.path.exists(venv_dst):
    shutil.rmtree(venv_dst)
shutil.copytree(venv_src, venv_dst)
print("复制完成")

print("\n[4/5] 压缩为 WxDown.zip...")
zip_path = os.path.join(base, "dist", "WxDown.zip")
if os.path.exists(zip_path):
    os.remove(zip_path)

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    wxdown_dir = os.path.join(base, "dist", "WxDown")
    for root, dirs, files in os.walk(wxdown_dir):
        for f in files:
            fp = os.path.join(root, f)
            arcname = os.path.relpath(fp, os.path.join(base, "dist"))
            zf.write(fp, arcname)

size_mb = os.path.getsize(zip_path) / 1024 / 1024
print(f"WxDown.zip: {size_mb:.2f} MB")

print("\n[5/5] 清理临时文件...")
shutil.rmtree(os.path.join(base, "build"), ignore_errors=True)
spec_file = os.path.join(base, "WxDown.spec")
if os.path.exists(spec_file):
    os.remove(spec_file)

print("\n========================================")
print("  打包完成！输出: dist/WxDown.zip")
print("========================================")
