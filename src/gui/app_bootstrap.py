"""Tkinter 应用启动前的环境与根窗口初始化。"""

from __future__ import annotations

import ctypes
import os
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


# 必须在导入 PaddleOCR 相关模块之前设置：Windows CPU 环境关闭
# oneDNN/MKLDNN 优化路径，规避 ConvertPirAttribute2RuntimeAttribute 异常。
def configure_runtime_environment() -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"


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

    root = tk.Tk()
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
