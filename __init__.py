import asyncio
import glob
import hashlib
import json
import logging
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path

from aiohttp import web
from server import PromptServer
from tqdm.auto import trange

import comfy.utils


WEB_DIRECTORY = "web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
HEADROOM = 32 * 1024 ** 3
_lock = threading.Lock()
_original_load_torch_file = comfy.utils.load_torch_file
log = logging.getLogger("ComfyUI-Librarian")


def _config():
    data = {"enabled": True, "parent_dir": "", "quota_gb": 256, "startup_check_disabled": False}
    if CONFIG_FILE.exists():
        data.update(json.loads(CONFIG_FILE.read_text()))
    return data


def _cache_root(cfg):
    if not cfg["parent_dir"]:
        return None
    return Path(cfg["parent_dir"]).expanduser() / ".comfyUI-Librarian"


def _header_hash(path):
    if path.lower().endswith((".safetensors", ".sft")):
        with open(path, "rb") as f:
            size = struct.unpack("<Q", f.read(8))[0]
            return hashlib.sha256(f.read(size)).hexdigest()
    return ""


def _cache_path(src, root):
    st = os.stat(src)
    h = hashlib.sha256()
    h.update(os.path.basename(src).encode("utf-8", "surrogateescape"))
    h.update(str(st.st_ctime_ns).encode())
    h.update(_header_hash(src).encode())
    digest = h.hexdigest()
    name = "".join(c if c.isalnum() or c in ".-_" else "_" for c in os.path.basename(src))[:120]
    return root / digest[:2] / f"{digest[2:]}--{name}"


def _samefs_marker(dst):
    return dst.parents[1] / ".markers" / dst.parent.name / f"{dst.name}.samefs"


def _same_filesystem(src, root):
    return os.stat(os.path.realpath(src)).st_dev == os.stat(os.path.realpath(root)).st_dev


def _cache_files(root):
    return [Path(p) for p in glob.glob(str(root / "??" / "*--*")) if os.path.isfile(p)]


def _cache_size(root):
    return sum(p.stat().st_size for p in _cache_files(root)) if root and root.exists() else 0


def _prune(root, quota, needed=0):
    files = sorted(_cache_files(root), key=lambda p: p.stat().st_atime)
    total = sum(p.stat().st_size for p in files)
    for p in files:
        free = shutil.disk_usage(root).free
        if total + needed <= quota and free >= HEADROOM + needed:
            break
        size = p.stat().st_size
        p.unlink(missing_ok=True)
        total -= size
        try:
            p.parent.rmdir()
        except OSError:
            pass


def _copy_with_progress(src, dst, size):
    chunk = 16 * 1024 * 1024
    desc = os.path.basename(src)
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst, trange(size, desc=desc, unit="B", unit_scale=True, unit_divisor=1024) as bar:
        while True:
            data = fsrc.read(chunk)
            if not data:
                break
            fdst.write(data)
            bar.update(len(data))
    shutil.copystat(src, dst)


def _cached(src):
    src = os.fspath(src)
    cfg = _config()
    if not cfg["enabled"]:
        return src
    if not cfg["parent_dir"]:
        return src
    root = _cache_root(cfg)
    if root.resolve() in Path(src).resolve().parents:
        return src
    dst = _cache_path(src, root)
    with _lock:
        root.mkdir(parents=True, exist_ok=True)
        if _same_filesystem(src, root):
            marker = _samefs_marker(dst)
            if not marker.exists():
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(f"same filesystem skip for {os.path.realpath(src)}\n")
                log.info("Cache root is on the same filesystem as %s. skipping cache", os.path.basename(src))
            return src
        if dst.exists():
            os.utime(dst, None)
            return str(dst)
        size = os.path.getsize(src)
        quota = int(float(cfg["quota_gb"]) * 1024 ** 3)
        _prune(root, quota, size)
        if size > quota or shutil.disk_usage(root).free < HEADROOM + size:
            return src
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="copy-", dir=dst.parent)
        os.close(fd)
        try:
            log.info("Cache miss on %s. populating cache", os.path.basename(src))
            _copy_with_progress(src, tmp, size)
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        _prune(root, quota)
        return str(dst)


def load_torch_file(ckpt, *args, **kwargs):
    try:
        ckpt = _cached(ckpt)
    except Exception:
        pass
    return _original_load_torch_file(ckpt, *args, **kwargs)


comfy.utils.load_torch_file = load_torch_file


@PromptServer.instance.routes.get("/librarian/config")
async def get_config(request):
    cfg = _config()
    root = _cache_root(cfg)
    return web.json_response({**cfg, "configured": CONFIG_FILE.exists() and bool(cfg["parent_dir"]), "cache_dir": str(root) if root else "", "used": _cache_size(root)})


@PromptServer.instance.routes.post("/librarian/config")
async def set_config(request):
    data = await request.json()
    cfg = {
        "enabled": bool(data.get("enabled")),
        "parent_dir": str(Path(data.get("parent_dir") or "").expanduser()) if data.get("parent_dir") else "",
        "quota_gb": max(1, float(data.get("quota_gb") or 1)),
        "startup_check_disabled": bool(data.get("startup_check_disabled")),
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    root = _cache_root(cfg)
    return web.json_response({**cfg, "configured": bool(cfg["parent_dir"]), "cache_dir": str(root) if root else "", "used": _cache_size(root)})


def _browse_directory():
    system = platform.system()
    if system == "Windows":
        script = "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.RootFolder=[System.Environment+SpecialFolder]::MyComputer; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
        return subprocess.check_output(["powershell", "-NoProfile", "-Command", script], text=True).strip()
    if system == "Darwin":
        script = 'POSIX path of (choose folder with prompt "Choose ComfyUI-Librarian cache parent")'
        return subprocess.check_output(["osascript", "-e", script], text=True).strip().rstrip("/")
    for cmd in (["zenity", "--file-selection", "--directory", "--title=Choose ComfyUI-Librarian cache parent"],
                ["kdialog", "--getexistingdirectory", str(Path.home())]):
        try:
            return subprocess.check_output(cmd, text=True).strip().rstrip("/")
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    return ""


@PromptServer.instance.routes.post("/librarian/browse")
async def browse(request):
    return web.json_response({"parent_dir": await asyncio.to_thread(_browse_directory)})
