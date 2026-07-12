"""Tkinter 应用启动前的环境与根窗口初始化。"""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:  # 依赖缺失时仍允许启动，只是不启用文件拖放。
    TkinterDnD = None


_ROOT_DND_METHODS = (
    "_substitute_dnd",
    "_dnd_bind",
    "dnd_bind",
    "drag_source_register",
    "drag_source_unregister",
    "drop_target_register",
    "drop_target_unregister",
    "platform_independent_types",
    "platform_specific_types",
    "get_dropfile_tempdir",
    "set_dropfile_tempdir",
)


def configure_runtime_environment() -> None:
    """Set environment variables and frozen-bundle compatibility patches.

    Must be called BEFORE importing any PaddleOCR / PaddleX modules.

    The key fix for frozen (PyInstaller) builds:
    - ``hooks/runtime_hook.py`` already patched ``importlib.metadata.version``
      so that ``is_dep_available()`` returns True for all bundled packages.
    - We additionally pre-import cv2 and pyclipper so they are in
      ``sys.modules`` before any PaddleX code tries to access them.
    - We also patch ``is_dep_available`` directly as a redundant safety net.
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"

    if not getattr(sys, "frozen", False):
        return

    # ── Frozen-bundle compatibility ─────────────────────────────────────
    _frozen_bootstrap()


def _frozen_bootstrap() -> None:
    """Apply frozen-bundle compatibility patches.

    This runs after the PyInstaller runtime hook has already patched
    ``importlib.metadata.version``.  We now pre-import critical modules
    and add a redundant patch on ``is_dep_available`` for defence in depth.
    """
    _patch_log = []

    try:
        # 1. Pre-import critical modules — they must be in sys.modules
        #    before PaddleX's lazy imports try to access them.
        import cv2  # noqa: F401
        import pyclipper  # noqa: F401
        _patch_log.append(f"cv2 {cv2.__version__} imported")

    except Exception as exc:
        _patch_log.append(f"PRE-IMPORT FAILED: {exc}")
        _write_log(_patch_log)
        return

    try:
        # 2. Patch is_dep_available as a redundant safety net.
        #    The runtime hook already patched importlib.metadata.version,
        #    so this should never actually be needed — but it's cheap and
        #    guarantees correctness even if some code path bypasses
        #    get_dep_version.
        from paddlex.utils.deps import is_dep_available as _orig

        _HEAVYWEIGHT = {
            "paddlepaddle", "onnxruntime", "torch",
            "tensorflow", "paddle-custom-device",
        }

        def _frozen_is_dep(dep, **kw):
            if dep in _HEAVYWEIGHT:
                return _orig(dep, **kw)
            return True

        import paddlex.utils.deps as _pxd
        _pxd.is_dep_available = _frozen_is_dep

        # Clear lru_cache to forget any stale False results
        for _attr in ("is_dep_available", "is_extra_available"):
            _fn = getattr(_pxd, _attr, None)
            if _fn is not None and hasattr(_fn, "cache_clear"):
                _fn.cache_clear()

        _patch_log.append("is_dep_available patched")

    except Exception as exc:
        _patch_log.append(f"PADDLEX PATCH FAILED: {exc}")

    _write_log(_patch_log)


def _write_log(lines: list[str]) -> None:
    """Write bootstrap log to a temp file for debugging frozen builds."""
    try:
        with open("/tmp/ocrtool_bootstrap.log", "w") as f:
            f.write("\n".join(lines))
    except Exception:
        pass


def _install_tkdnd_root_methods(root: tk.Tk) -> None:
    """Bridge tkinterdnd2 wrapper methods onto an existing Tk root."""

    if TkinterDnD is None:
        return
    wrapper = getattr(TkinterDnD, "DnDWrapper", None)
    if wrapper is None:
        return

    for attribute in ("_subst_format_dnd", "_subst_format_str_dnd"):
        if not hasattr(root, attribute) and hasattr(wrapper, attribute):
            setattr(root, attribute, getattr(wrapper, attribute))

    for method_name in _ROOT_DND_METHODS:
        if hasattr(root, method_name):
            continue
        method = getattr(wrapper, method_name, None)
        if method is not None:
            setattr(root, method_name, method.__get__(root, type(root)))


def create_root() -> tk.Tk:
    """Create the root hidden, then add drag-and-drop support when available."""

    # On macOS .app bundles Tk may crash inside TkpSetMainMenubar when the
    # application name passed to NSMenuItem is empty.  Explicitly passing a
    # className prevents Tk from reading a nil/empty CFBundleName.
    root = tk.Tk(className="404 Found OCR")
    root._tkdnd_enabled = False
    root.withdraw()

    if TkinterDnD is None:
        print("[INFO] tkinterdnd2 未安装，文件拖拽功能不可用。")
        return root
    try:
        TkinterDnD.require(root)
        _install_tkdnd_root_methods(root)
        root._tkdnd_enabled = hasattr(root, "drop_target_register") and hasattr(
            root, "dnd_bind"
        )
        if not root._tkdnd_enabled:
            print("[WARNING] 拖拽支持已加载，但根窗口缺少注册方法，文件拖拽功能将不可用。")
    except (RuntimeError, tk.TclError) as exc:
        print(f"[WARNING] 无法加载拖拽支持 ({exc})，文件拖拽功能将不可用。")
    return root


def enable_high_dpi_mode() -> None:
    """在 Windows 上启用高 DPI 感知，避免 Tkinter 界面发虚。"""

    if os.name != "nt":
        return

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
