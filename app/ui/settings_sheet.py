"""Settings: profile, Gemini AI, appearance, and the library's Git versioning."""
from __future__ import annotations

import subprocess
import sys
from typing import Callable

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QSizePolicy, QWidget

from ..constants import API_KEY_URL, MODE_FACILITATOR, MODE_INTERN, MODELS
from ..core import settings as S
from ..theme import font, palette, rgba, system_color, theme
from .controls import ActivityIndicator, IconButton, SegmentedControl, Switch, make_button, on_theme_change
from .forms import ElidedLabel, StatusLabel, fit_row, keep_thread, tint_badges
from .sheet import GroupBox, Sheet, footnote, section_header

_APPEARANCES = ["system", "light", "dark"]
_MODES = [MODE_FACILITATOR, MODE_INTERN]


def _safe(fn: Callable, default=None):
    try:
        return fn()
    except Exception:
        return default


class SettingsSheet(Sheet):
    """System Settings-style preferences sheet."""

    mode_changed = Signal(str)
    api_key_changed = Signal()

    def __init__(self, host: QWidget, settings, library, git) -> None:
        super().__init__(host, "Settings", 560)
        self._s = settings
        self._lib = library
        self._git = git
        self._loading = False
        self._initial_user = ""
        self._check_run = 0
        self._git_op = ""
        self._build()
        self._connect_git()

    # ------------------------------------------------------------------ building
    def _row(self, group: GroupBox, label: str | None, control, icon: str | None = None, color: str = "blue",
             description: str = "", fit: bool = True) -> QWidget:
        row = group.add_row(label, control, icon=icon, icon_color=system_color(color) if icon else None,
                            description=description)
        if icon:
            tint_badges(row, color)
        if fit and not description:
            fit_row(row)
        return row

    def _build(self) -> None:
        b = self.body_layout
        b.setSpacing(8)

        # Profile
        b.addWidget(section_header("Profile"))
        g = GroupBox()
        self._user = QLineEdit()
        self._user.setFont(font("body"))
        self._user.setPlaceholderText("Your name")
        self._user.setMinimumWidth(240)
        self._user.editingFinished.connect(self._save_user)
        self._row(g, "Your Name", self._user, "person", "blue")
        self._mode = SegmentedControl(["Facilitator", "Intern"])
        self._mode.setFixedWidth(200)
        self._mode.currentChanged.connect(self._on_mode)
        self._row(g, "Mode", self._mode, "graduationcap", "indigo",
                  description="Interns can browse and download, but not edit.")
        b.addWidget(g)
        b.addSpacing(6)

        # Gemini AI
        b.addWidget(section_header("Gemini AI"))
        g = GroupBox()
        key_ctrl = QHBoxLayout()
        key_ctrl.setSpacing(4)
        self._key = QLineEdit()
        self._key.setFont(font("body"))
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Paste your API key")
        self._key.setMinimumWidth(200)
        self._key.editingFinished.connect(self._save_key)
        key_ctrl.addWidget(self._key, 1)
        self._eye = IconButton("eye", "Show Key", 26, 15)
        self._eye.clicked.connect(self._toggle_key_visible)
        key_ctrl.addWidget(self._eye)
        key_ctrl.addSpacing(4)
        self._test = make_button("Test")
        self._test.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._test.clicked.connect(self._test_key)
        key_ctrl.addWidget(self._test)
        self._row(g, "API Key", key_ctrl, "sparkles", "purple")
        check = QHBoxLayout()
        check.setSpacing(8)
        check.setContentsMargins(34, 0, 0, 0)
        self._check_spin = ActivityIndicator(14)
        check.addWidget(self._check_spin)
        self._check_status = StatusLabel()
        check.addWidget(self._check_status, 1)
        self._check_row = g.add_row(None, check)
        self._check_row.setMinimumHeight(30)
        self._check_row.hide()
        self._model = QComboBox()
        self._model.setFont(font("body"))
        self._model.setMinimumWidth(220)
        for i, (mid, name, desc) in enumerate(MODELS):
            self._model.addItem(name, mid)
            self._model.setItemData(i, desc, Qt.ItemDataRole.ToolTipRole)
        self._model.currentIndexChanged.connect(self._on_model)
        self._row(g, "Model", self._model, "cpu", "purple")
        b.addWidget(g)
        self._key_source = footnote("")
        self._key_source.hide()
        b.addWidget(self._key_source)
        self._ai_note = footnote("", rich=True)
        on_theme_change(self._ai_note, self._update_ai_note)
        b.addWidget(self._ai_note)
        b.addSpacing(6)

        # Appearance
        b.addWidget(section_header("Appearance"))
        g = GroupBox()
        self._appearance = SegmentedControl(["System", "Light", "Dark"])
        self._appearance.setFixedWidth(240)
        self._appearance.currentChanged.connect(self._on_appearance)
        self._row(g, "Appearance", self._appearance, "appearance", "gray")
        b.addWidget(g)
        b.addSpacing(6)

        # Library & Git
        b.addWidget(section_header("Library & Git"))
        g = GroupBox()
        loc = QHBoxLayout()
        loc.setSpacing(8)
        self._path = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self._path.setFont(font("callout"))
        self._path.setMinimumWidth(120)
        self._path.setMaximumWidth(230)
        self._path.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._path.customContextMenuRequested.connect(self._path_menu)
        self._path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._path.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        loc.addWidget(self._path, 1)
        reveal = make_button("Show in Explorer" if sys.platform == "win32" else "Show in Finder", "plain")
        reveal.clicked.connect(self._reveal_library)
        loc.addWidget(reveal)
        self._row(g, "Library Location", loc, "folder_fill", "blue")

        self._git_status = QLabel()
        self._git_status.setFont(font("callout"))
        self._row(g, "Git", self._git_status, "branch", "orange")

        remote = QHBoxLayout()
        remote.setSpacing(8)
        self._remote_label = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self._remote_label.setFont(font("callout"))
        self._remote_label.setMaximumWidth(230)
        self._remote_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        remote.addWidget(self._remote_label, 1)
        self._remote_btn = make_button("Add Remote\u2026", "plain")
        self._remote_btn.clicked.connect(self._edit_remote)
        remote.addWidget(self._remote_btn)
        self._remote_edit = QLineEdit()
        self._remote_edit.setFont(font("body"))
        self._remote_edit.setPlaceholderText("https://github.com/you/library.git")
        self._remote_edit.setMinimumWidth(200)
        self._remote_edit.installEventFilter(self)
        self._remote_edit.hide()
        remote.addWidget(self._remote_edit, 1)
        self._remote_save = make_button("Save")
        self._remote_save.clicked.connect(self._save_remote)
        self._remote_save.hide()
        remote.addWidget(self._remote_save)
        self._row(g, "Remote", remote, "sync", "orange")

        self._git_switch = Switch()
        self._git_switch.toggled.connect(self._on_git_enabled)
        self._row(g, "Record changes with Git", self._git_switch, "history", "orange")
        self._push_switch = Switch()
        self._push_switch.toggled.connect(self._on_auto_push)
        self._row(g, "Push after each change", self._push_switch, "arrow_up", "orange")

        sync = QHBoxLayout()
        sync.setSpacing(8)
        self._sync_spin = ActivityIndicator(14)
        sync.addWidget(self._sync_spin)
        self._sync_status = StatusLabel()
        sync.addWidget(self._sync_status, 1)
        sync.addStretch(0)
        self._pull = make_button("Pull Latest")
        self._pull.clicked.connect(self._do_pull)
        self._push = make_button("Push Now")
        self._push.clicked.connect(self._do_push)
        for btn in (self._pull, self._push):
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            sync.addWidget(btn)
        self._row(g, None, sync)
        b.addWidget(g)
        self._git_note = footnote("Every upload, edit and classwork entry is saved as a Git commit in the library "
                                  "folder, so nothing is lost and changes can be shared.")
        b.addWidget(self._git_note)

        self._error = StatusLabel()
        b.addWidget(self._error)
        done, _ = self.add_footer_buttons("Done", None)
        done.clicked.connect(self._done)
        on_theme_change(self, self._style_labels)

    def _style_labels(self) -> None:
        pal = palette()
        for lbl in (self._path, self._git_status, self._remote_label):
            lbl.setStyleSheet(f"color: {rgba(pal.secondary_label)};")

    def _update_ai_note(self) -> None:
        link = rgba(palette().link)
        self._ai_note.setText(
            "Gemini is only used to suggest modules, topics and keywords. Your key is stored on this computer only. "
            f"<a href=\"{API_KEY_URL}\" style=\"color: {link}; text-decoration: none;\">Get an API key</a>")

    def _connect_git(self) -> None:
        g = self._git
        if g is None:
            return
        for name, slot in (("pulled", self._on_pulled), ("pushed", self._on_pushed),
                           ("operation_failed", self._on_git_failed), ("status_changed", self._on_git_status)):
            sig = getattr(g, name, None)
            if sig is not None:
                try:
                    sig.connect(slot)
                except Exception:
                    pass

    # ------------------------------------------------------------------ loading
    def on_open(self) -> None:
        self._loading = True
        try:
            s = self._s
            self._initial_user = s.get(S.KEY_USER_NAME) or s.user_name()
            self._user.setText(self._initial_user)
            self._mode.setCurrentIndex(1 if s.mode() == MODE_INTERN else 0)
            self._load_key()
            idx = self._model.findData(s.model())
            self._model.setCurrentIndex(max(0, idx))
            app = s.appearance()
            self._appearance.setCurrentIndex(_APPEARANCES.index(app) if app in _APPEARANCES else 0)
            self._cancel_remote_edit()
            self._refresh_git()
        finally:
            self._loading = False
        self._check_row.hide()
        self._error.clear()
        if not self._sync_spin.isVisible():
            self._sync_status.clear()

    def _load_key(self) -> None:
        source = _safe(self._s.api_key_source, "")
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._eye.setIconName("eye")
        self._eye.setToolTip("Show Key")
        if source in ("env", "dotenv"):
            self._key.setText(_safe(self._s.api_key, ""))
            self._key.setEnabled(False)
            self._eye.setEnabled(False)
            where = "your environment" if source == "env" else "the .env file"
            self._key_source.setText(f"Using GEMINI_API_KEY from {where}.")
            self._key_source.show()
        else:
            self._key.setText(self._s.get(S.KEY_API_KEY) or "")
            self._key.setEnabled(True)
            self._eye.setEnabled(True)
            self._key_source.hide()

    def _refresh_git(self) -> None:
        root = str(self._lib.root)
        self._path.setText(root)
        self._path.setToolTip(root)
        g = self._git
        avail = bool(_safe(g.available, False)) if g is not None else False
        repo = bool(_safe(g.is_repo, False)) if avail else False
        enabled = self._s.git_enabled()
        if g is None or not avail:
            text = "Git isn\u2019t installed"
        elif not repo:
            text = "Not a Git repository"
        elif not enabled:
            text = "Not recording changes"
        else:
            text = f"Tracking changes on branch {_safe(g.branch, '') or 'main'}"
        self._git_status.setText(text)
        url = (_safe(g.remote_url, "") or "") if repo else ""
        has_remote = bool(url) or bool(repo and _safe(g.has_remote, False))
        self._remote_label.setText(url or "No remote")
        self._remote_label.setToolTip(url)
        self._remote_btn.setText("Change\u2026" if has_remote else "Add Remote\u2026")
        self._remote_btn.setEnabled(repo)
        was = self._loading
        self._loading = True
        self._git_switch.setChecked(enabled)
        self._git_switch.setEnabled(avail)
        self._push_switch.setChecked(self._s.auto_push() and has_remote)
        self._push_switch.setEnabled(avail and repo and has_remote and enabled)
        self._push_switch.setToolTip("" if has_remote else "Add a remote first.")
        self._loading = was
        can_sync = avail and repo and has_remote
        self._pull.setEnabled(can_sync and not self._git_op)
        self._push.setEnabled(can_sync and not self._git_op)
        tip = "" if has_remote else "Add a remote to sync with others."
        self._pull.setToolTip(tip)
        self._push.setToolTip(tip)

    # ------------------------------------------------------------------ profile & appearance
    def _save_user(self) -> None:
        if self._loading:
            return
        name = self._user.text().strip()
        if name == self._initial_user:
            return
        try:
            self._s.set(S.KEY_USER_NAME, name or None)
            if self._git is not None:
                self._git.set_user_name(name)
            self._initial_user = name
        except Exception as exc:
            self._show_error(f"Couldn\u2019t save your name: {exc}")

    def _on_mode(self, index: int) -> None:
        if self._loading:
            return
        mode = _MODES[max(0, min(index, 1))]
        try:
            self._s.set(S.KEY_MODE, mode)
        except Exception as exc:
            self._show_error(f"Couldn\u2019t save the mode: {exc}")
            return
        self.mode_changed.emit(mode)

    def _on_appearance(self, index: int) -> None:
        if self._loading:
            return
        value = _APPEARANCES[max(0, min(index, 2))]
        try:
            self._s.set(S.KEY_APPEARANCE, value)
        except Exception:
            pass
        theme().set_mode(value)

    # ------------------------------------------------------------------ Gemini
    def _toggle_key_visible(self) -> None:
        hidden = self._key.echoMode() == QLineEdit.EchoMode.Password
        self._key.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self._eye.setIconName("eye_slash" if hidden else "eye")
        self._eye.setToolTip("Hide Key" if hidden else "Show Key")

    def _save_key(self) -> None:
        if self._loading or _safe(self._s.api_key_source, "") in ("env", "dotenv"):
            return
        new = self._key.text().strip()
        old = (self._s.get(S.KEY_API_KEY) or "").strip()
        if new == old:
            return
        try:
            self._s.set_api_key(new)
        except Exception as exc:
            self._show_error(f"Couldn\u2019t save the API key: {exc}")
            return
        self._check_run += 1
        self._check_spin.stop()
        self._check_row.hide()
        self._test.setEnabled(True)
        self.api_key_changed.emit()

    def _on_model(self, _index: int) -> None:
        if self._loading:
            return
        model = self._model.currentData()
        if model:
            try:
                self._s.set(S.KEY_MODEL, model)
            except Exception as exc:
                self._show_error(f"Couldn\u2019t save the model: {exc}")

    def _test_key(self) -> None:
        self._save_key()
        key = self._key.text().strip() or _safe(self._s.api_key, "")
        self._check_row.show()
        if not key:
            self._check_status.set_status("Paste an API key first.", "error")
            self._relayout()
            return
        try:
            from ..core.ai import KeyCheckWorker
            worker = KeyCheckWorker(key, self._model.currentData())
        except Exception:
            self._check_status.set_status("Gemini isn\u2019t available in this installation.", "error")
            self._relayout()
            return
        self._check_run += 1
        worker.run_id = self._check_run
        worker.result.connect(self._on_key_result)
        keep_thread(worker)
        self._test.setEnabled(False)
        self._check_spin.start()
        self._check_status.set_status("Checking\u2026")
        self._relayout()
        worker.start()

    def _on_key_result(self, ok: bool, message: str) -> None:
        if getattr(self.sender(), "run_id", -1) != self._check_run:
            return
        self._check_spin.stop()
        self._test.setEnabled(True)
        if ok:
            self._check_status.set_status("Connected", "ok")
        else:
            self._check_status.set_status(message or "The key didn\u2019t work.", "error")
        self._relayout()

    # ------------------------------------------------------------------ library & git
    def _reveal_library(self) -> None:
        root = self._lib.root
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(root)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
        except Exception as exc:
            self._show_error(f"Couldn\u2019t open the library folder: {exc}")

    def _path_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setFont(font("body"))
        copy = menu.addAction("Copy Path")
        if menu.exec(self._path.mapToGlobal(pos)) is copy:
            QGuiApplication.clipboard().setText(str(self._lib.root))

    def _edit_remote(self) -> None:
        self._remote_label.hide()
        self._remote_btn.hide()
        self._remote_edit.setText(_safe(self._git.remote_url, "") if self._git is not None else "")
        self._remote_edit.show()
        self._remote_save.show()
        self._remote_edit.setFocus()
        self._remote_edit.selectAll()

    def _cancel_remote_edit(self) -> None:
        self._remote_edit.hide()
        self._remote_save.hide()
        self._remote_label.show()
        self._remote_btn.show()

    def _save_remote(self) -> None:
        url = self._remote_edit.text().strip()
        current = _safe(self._git.remote_url, "") if self._git is not None else ""
        if url and url != current and self._git is not None:
            try:
                ok = self._git.set_remote(url)
            except Exception as exc:
                self._show_error(f"Couldn\u2019t set the remote: {exc}")
                return
            if ok is False:
                self._show_error("Couldn\u2019t set the remote. Check the URL and try again.")
                return
            self._error.clear()
        self._cancel_remote_edit()
        self._refresh_git()

    def _on_git_enabled(self, on: bool) -> None:
        if self._loading:
            return
        try:
            self._s.set_bool(S.KEY_GIT_ENABLED, on)
            if self._git is not None:
                self._git.set_enabled(on)
        except Exception as exc:
            self._show_error(f"Couldn\u2019t change Git recording: {exc}")
        self._refresh_git()

    def _on_auto_push(self, on: bool) -> None:
        if self._loading:
            return
        try:
            self._s.set_bool(S.KEY_AUTO_PUSH, on)
            if self._git is not None:
                self._git.set_auto_push(on)
        except Exception as exc:
            self._show_error(f"Couldn\u2019t change automatic pushing: {exc}")

    def _start_git_op(self, op: str, text: str, fn: Callable[[], None]) -> None:
        if self._git is None or self._git_op:
            return
        self._git_op = op
        self._sync_spin.start()
        self._sync_status.set_status(text)
        self._refresh_git()
        try:
            fn()
        except Exception as exc:
            self._on_git_failed(str(exc))

    def _do_pull(self) -> None:
        self._start_git_op("pull", "Pulling the latest changes\u2026", self._git.pull)

    def _do_push(self) -> None:
        self._start_git_op("push", "Pushing\u2026", self._git.push)

    def _finish_git_op(self, text: str, kind: str) -> None:
        self._git_op = ""
        self._sync_spin.stop()
        self._sync_status.set_status(text, kind)
        self._refresh_git()
        self._relayout()

    def _on_pulled(self) -> None:
        if self._git_op != "pull":
            return
        try:
            self._lib.reload()
        except Exception as exc:
            self._finish_git_op(f"Pulled, but the library couldn\u2019t be reloaded: {exc}", "error")
            return
        self._finish_git_op("Up to date with the remote.", "ok")

    def _on_pushed(self) -> None:
        if self._git_op == "push":
            self._finish_git_op("Pushed your changes.", "ok")

    def _on_git_failed(self, message: str) -> None:
        if self._git_op:
            self._finish_git_op(message or "The Git operation failed.", "error")
        elif self.isVisible():
            self._sync_status.set_status(message or "The Git operation failed.", "error")
            self._relayout()

    def _on_git_status(self) -> None:
        if self.isVisible():
            self._refresh_git()

    # ------------------------------------------------------------------ misc
    def eventFilter(self, obj, event):
        if obj is self._remote_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._save_remote()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_remote_edit()
                return True
        return super().eventFilter(obj, event)

    def _show_error(self, message: str) -> None:
        self._error.set_status(message, "error")
        self._relayout()

    def _relayout(self) -> None:
        self.relayout()

    def _done(self) -> None:
        self._save_user()
        self._save_key()
        if self._remote_edit.isVisible():
            self._save_remote()
        self.accept()
