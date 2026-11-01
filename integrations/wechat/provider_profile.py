"""Explicit Windows operator profile, separate from ISB business configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from .model import ConnectorError
from .vision_eval import BASE_URL, FREE_MODELS

ROOT = Path(__file__).resolve().parents[2]


def profile_path() -> Path:
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        raise ConnectorError("windows_profile_required")
    return Path(os.environ["LOCALAPPDATA"]) / "ClassMatter" / "connector-secrets" / "zhipu-standard.dpapi"


def _codec(value: bytes, *, decrypt=False) -> bytes:
    # Reuse existing current-user DPAPI. This import does not provision/connect a DB.
    source = str(ROOT / "backend" / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from class_os.infrastructure.local_runtime import protect
    return protect(value, decrypt=decrypt)


def _validate(profile: dict):
    if (not isinstance(profile, dict) or set(profile) != {"kind", "provider", "base_url", "model", "api_key"}
            or profile.get("kind") != "classmatter.connector-provider-secret.v1"
            or profile.get("provider") != "zhipu" or profile.get("base_url") != BASE_URL
            or profile.get("model") not in FREE_MODELS):
        raise ConnectorError("invalid_local_provider_profile")
    key = profile.get("api_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 2048 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ConnectorError("invalid_local_provider_key")


def load_profile(path: Path | None = None, *, codec=None) -> dict:
    path = path if path is not None else profile_path()
    try:
        if path.is_symlink() or not 1 <= path.stat().st_size <= 16384:
            raise ConnectorError("invalid_local_provider_profile")
        profile = json.loads((codec or _codec)(path.read_bytes(), decrypt=True))
        _validate(profile)
        return profile
    except Exception:
        raise ConnectorError("local_provider_profile_unavailable") from None


def store_profile(key: str, model: str, path: Path | None = None, *, codec=None):
    profile = {"kind": "classmatter.connector-provider-secret.v1", "provider": "zhipu",
               "base_url": BASE_URL, "model": model, "api_key": key.strip()}
    _validate(profile)
    try:
        sealed = (codec or _codec)(json.dumps(profile, separators=(",", ":")).encode("utf-8"))
        if not isinstance(sealed, bytes) or not 1 <= len(sealed) <= 16384:
            raise ConnectorError("invalid_local_provider_profile")
        path = path if path is not None else profile_path()
        if path.is_symlink():
            raise ConnectorError("invalid_local_provider_profile")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(sealed)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    except Exception:
        raise ConnectorError("local_provider_profile_save_failed") from None


def main():
    import tkinter as tk
    from tkinter import ttk
    window = tk.Tk()
    smoke = "--smoke" in sys.argv
    if smoke:
        window.withdraw()
    window.title("ClassMatter · 智谱免费视觉模型配置")
    window.geometry("700x360")
    frame = ttk.Frame(window, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="本机智谱 Key / 免费型号", font=("Microsoft YaHei UI", 16)).pack(anchor="w")
    ttk.Label(frame, text="只使用标准 API；密钥按当前 Windows 用户加密保存。保存不联网、不测试、不写业务库。", wraplength=640).pack(anchor="w", pady=10)
    selected = tk.StringVar(value=FREE_MODELS[0])
    try:
        selected.set(load_profile()["model"])
        present = True
    except ConnectorError:
        present = False
    ttk.Combobox(frame, values=FREE_MODELS, textvariable=selected, state="readonly").pack(fill="x", pady=5)
    ttk.Label(frame, text="粘贴完整 Key；已有配置时留空可复用原 Key，仅切换型号：").pack(anchor="w")
    entry = ttk.Entry(frame, show="●")
    entry.pack(fill="x", pady=8)
    status = tk.StringVar(value="已有本机配置，未显示密钥。" if present else "尚无可读的本机配置。")
    ttk.Label(frame, textvariable=status, wraplength=640).pack(anchor="w", pady=8)
    def save():
        try:
            key = entry.get().strip() or load_profile()["api_key"]
            store_profile(key, selected.get())
            entry.delete(0, "end")
            status.set("已加密保存。尚未联网验证；可回工作台点击免费视觉自测。")
        except ConnectorError:
            status.set("保存失败：请检查完整 Key、免费型号和当前用户的本机环境。")
    ttk.Button(frame, text="加密保存", command=save).pack(anchor="e", pady=8)
    entry.focus_set()
    if smoke:
        assert entry.cget("show") == "●"
        assert selected.get() in FREE_MODELS
        window.after(20, window.destroy)
    window.mainloop()
    if smoke:
        print("Masked native provider configuration smoke passed; no save or network")


if __name__ == "__main__":
    main()
