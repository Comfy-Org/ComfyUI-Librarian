import glob
import hashlib
import json
import os
import shutil
import struct
import tempfile
import threading
from pathlib import Path

from aiohttp import web
from server import PromptServer

import comfy.utils


WEB_DIRECTORY = "web"
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
HEADROOM = 32 * 1024 ** 3
_lock = threading.Lock()
_original_load_torch_file = comfy.utils.load_torch_file


def _config():
    data = {"enabled": False, "parent_dir": str(Path.home()), "quota_gb": 256}
    if CONFIG_FILE.exists():
        data.update(json.loads(CONFIG_FILE.read_text()))
    return data


def _cache_root(cfg):
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


def _cache_files(root):
    return [Path(p) for p in glob.glob(str(root / "??" / "*--*")) if os.path.isfile(p)]


def _cache_size(root):
    return sum(p.stat().st_size for p in _cache_files(root)) if root.exists() else 0


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


def _cached(src):
    src = os.fspath(src)
    cfg = _config()
    if not cfg["enabled"]:
        return src
    root = _cache_root(cfg)
    if root.resolve() in Path(src).resolve().parents:
        return src
    dst = _cache_path(src, root)
    with _lock:
        if dst.exists():
            os.utime(dst, None)
            return str(dst)
        root.mkdir(parents=True, exist_ok=True)
        size = os.path.getsize(src)
        quota = int(float(cfg["quota_gb"]) * 1024 ** 3)
        _prune(root, quota, size)
        if size > quota or shutil.disk_usage(root).free < HEADROOM + size:
            return src
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="copy-", dir=dst.parent)
        os.close(fd)
        try:
            shutil.copy2(src, tmp)
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
    return web.json_response({**cfg, "cache_dir": str(root), "used": _cache_size(root)})


@PromptServer.instance.routes.post("/librarian/config")
async def set_config(request):
    data = await request.json()
    cfg = {
        "enabled": bool(data.get("enabled")),
        "parent_dir": str(Path(data.get("parent_dir") or Path.home()).expanduser()),
        "quota_gb": max(1, float(data.get("quota_gb") or 1)),
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    return web.json_response({**cfg, "cache_dir": str(_cache_root(cfg)), "used": _cache_size(_cache_root(cfg))})
