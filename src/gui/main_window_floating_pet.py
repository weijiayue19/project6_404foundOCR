"""Floating-pet and minimize/drop behavior for the main OCR window."""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from src.ocr_engine import OcrMode


class MainWindowFloatingPetMixin:
    """Mixin for the dinosaur pet, workbench minimize/restore, and pet drop flow.

    Expects MainWindow attributes such as root, _floating_pet, status_var,
    recognition_mode, mode_switch_var, image_path, and OCR/drop helper methods.
    """

    def _on_root_unmap(self, event: tk.Event) -> None:
        """Turn direct root minimization into the internal floating-pet state."""

        if event.widget is not self.root:
            return
        if self._is_quitting or self._is_hiding_to_pet or self._is_restoring_from_pet:
            return
        self._cancel_after_callback("_minimize_after_id")
        self._minimize_after_id = self.root.after_idle(self._hide_to_pet_if_iconified)

    def _has_visible_child_toplevel(self) -> bool:
        """Return whether an app child window is currently mapped or minimized."""

        def has_visible_toplevel(widget: tk.Misc) -> bool:
            for child in widget.winfo_children():
                if isinstance(child, tk.Toplevel):
                    try:
                        if child.state() != "withdrawn":
                            return True
                    except tk.TclError:
                        continue
                if has_visible_toplevel(child):
                    return True
            return False

        try:
            return has_visible_toplevel(self.root)
        except tk.TclError:
            return False

    def _hide_to_pet_if_iconified(self) -> None:
        self._minimize_after_id = None
        if self._is_quitting or self._is_hiding_to_pet or self._is_restoring_from_pet:
            return
        try:
            state = self.root.state()
        except tk.TclError:
            return
        if state == "iconic":
            self.hide_to_pet()

    def hide_to_pet(self) -> None:
        """Hide the workbench and show the dinosaur pet without stopping OCR."""

        if self._is_quitting or self._is_restoring_from_pet:
            return
        self._is_hiding_to_pet = True
        try:
            pet_visible = self._floating_pet.show()
            if pet_visible:
                self._set_workbench_animation_paused(True)
                self.root.withdraw()
            else:
                self._restore_workbench_after_pet_failure()
        except tk.TclError:
            self._restore_workbench_after_pet_failure()
        finally:
            try:
                self.root.after_idle(lambda: setattr(self, "_is_hiding_to_pet", False))
            except tk.TclError:
                self._is_hiding_to_pet = False

    def _restore_workbench_after_pet_failure(self) -> None:
        try:
            self._floating_pet.hide()
            self._set_workbench_animation_paused(False)
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def restore_from_pet(self) -> None:
        """Restore the workbench from the dinosaur pet window."""

        if self._is_quitting or self._is_restoring_from_pet:
            return
        self._is_restoring_from_pet = True
        try:
            self._floating_pet.hide()
            self.root.deiconify()
            self.root.lift()
            self._set_workbench_animation_paused(False)
            try:
                self.root.focus_force()
            except tk.TclError:
                self.root.focus_set()
        except tk.TclError:
            pass
        finally:
            try:
                self.root.after_idle(lambda: setattr(self, "_is_restoring_from_pet", False))
            except tk.TclError:
                self._is_restoring_from_pet = False

    def _mark_floating_pet_drop_started(self, event: object) -> None:
        self._floating_pet_drop_guard_until = time.monotonic() + self.FLOATING_PET_DROP_GUARD_SECONDS
        try:
            paths = self._paths_from_drop_data(getattr(event, "data", ""))
        except Exception:
            self._floating_pet_drop_signature = None
        else:
            self._floating_pet_drop_signature = self._drop_paths_signature(paths)
        try:
            self.root.after_idle(self._withdraw_root_for_pet_drop)
        except (AttributeError, tk.TclError):
            pass

    @staticmethod
    def _drop_paths_signature(paths: list[Path]) -> tuple[str, ...]:
        return tuple(str(path) for path in paths)

    def _is_recent_floating_pet_root_drop(self, paths: list[Path]) -> bool:
        if time.monotonic() > getattr(self, "_floating_pet_drop_guard_until", 0.0):
            return False
        signature = self._drop_paths_signature(paths)
        pet_signature = getattr(self, "_floating_pet_drop_signature", None)
        return pet_signature is None or signature == pet_signature

    def _remember_floating_pet_drop_paths(self, paths: list[Path]) -> None:
        self._floating_pet_drop_guard_until = time.monotonic() + self.FLOATING_PET_DROP_GUARD_SECONDS
        self._floating_pet_drop_signature = self._drop_paths_signature(paths)

    def _show_drop_mode_prompt(self, paths: list[Path], *, keep_root_hidden: bool = False) -> None:
        self._pending_pet_drop_paths = list(paths)
        self._pending_pet_drop_keep_root_hidden = (
            getattr(self, "_pending_pet_drop_keep_root_hidden", False) or keep_root_hidden
        )
        self.status_var.set("请选择识别模式，选择后导入文件")
        if keep_root_hidden:
            self._withdraw_root_for_pet_drop()
        self._floating_pet.show_mode_prompt()

    def _start_pending_drop_with_mode(self, mode: str) -> None:
        selected_mode: OcrMode = "document" if mode == "document" else "text"
        paths = list(self._pending_pet_drop_paths)
        keep_root_hidden = self._pending_pet_drop_keep_root_hidden or self._should_keep_root_hidden_for_pet_drop()
        self._pending_pet_drop_paths = []
        self._pending_pet_drop_keep_root_hidden = False
        if not paths:
            self._floating_pet.reset_mode_choice()
            return

        def setup_mode_then_import() -> None:
            try:
                if keep_root_hidden:
                    self._withdraw_root_for_pet_drop()
                if self.recognition_mode is None:
                    self._select_mode(selected_mode)
                    if keep_root_hidden:
                        self._withdraw_root_for_pet_drop()
                else:
                    self.recognition_mode = selected_mode
                    self.mode_switch_var.set(self._recognition_mode_name(selected_mode))
                self._floating_pet.clear_assistant_panel()
            except Exception as exc:
                self._floating_pet.reset_mode_choice()
                messagebox.showerror("无法进入识别模式", str(exc))
                self.status_var.set("识别模式初始化失败")
                return

            def accept_import() -> None:
                self._import_dropped_images_then_start(paths, keep_root_hidden=keep_root_hidden)

            try:
                self.root.after(40, accept_import)
            except (AttributeError, tk.TclError):
                try:
                    self.root.after_idle(accept_import)
                except (AttributeError, tk.TclError):
                    self._floating_pet.reset_mode_choice()

        try:
            self.root.after_idle(setup_mode_then_import)
        except (AttributeError, tk.TclError):
            self._floating_pet.reset_mode_choice()

    def _should_keep_root_hidden_for_pet_drop(self) -> bool:
        try:
            state = self.root.state()
        except (tk.TclError, AttributeError):
            return False
        return state in {"withdrawn", "iconic"}

    def _withdraw_root_for_pet_drop(self) -> None:
        self._is_hiding_to_pet = True
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        finally:
            try:
                self.root.after_idle(lambda: setattr(self, "_is_hiding_to_pet", False))
            except tk.TclError:
                self._is_hiding_to_pet = False

    def _show_pet_drop_completion(self) -> None:
        if not self._pet_drop_recognition_active:
            return
        self._pet_drop_recognition_active = False
        self._floating_pet.set_state("done")
        self._floating_pet.show_completion_message()

    def _clear_pet_drop_recognition(self) -> None:
        if self._pet_drop_recognition_active:
            self._floating_pet.set_state("idle")
        self._pet_drop_recognition_active = False

    def _set_workbench_animation_paused(self, paused: bool) -> None:
        process_rail = getattr(self, "process_rail", None)
        try:
            exists = process_rail is not None and process_rail.winfo_exists()
        except tk.TclError:
            return
        if exists:
            process_rail.set_animation_paused(paused)
