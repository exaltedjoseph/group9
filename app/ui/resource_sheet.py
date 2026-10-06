"""Add / edit a resource: file drop zone, Gemini suggestions and the metadata form."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QSizePolicy, QWidget

from .. import icons
from ..constants import API_KEY_URL, KIND_NAMES
from ..core.library import LibraryError
from ..core.models import Resource, Suggestion
from ..theme import font, palette, rgba, system_color
from .controls import ActivityIndicator, make_button, on_theme_change
from .forms import (DropZone, KindCombo, ModuleCombo, SparkleBadge, StatusLabel, TokenField, TopicCombo,
                    add_label_accessory, fit_row, keep_thread, merge_keywords, prettify_stem, tint_badges)
from .sheet import GroupBox, Sheet

EXCERPT_CHARS = 24_000
_SUBTITLE = "Interns will find it under the module and topic you choose."


def _extract_excerpt(path: Path) -> str:
    try:
        from ..core.extract import extract_text
    except Exception:
        return ""
    try:
        return (extract_text(path) or "")[:EXCERPT_CHARS]
    except Exception:
        return ""


class _TextJob(QThread):
    """Builds the text excerpt for the AI request off the GUI thread."""

    done = Signal(str)

    def __init__(self, fn: Callable[[], str], run_id: int, source: Path) -> None:
        super().__init__()
        self._fn = fn
        self.run_id = run_id
        self.source = source

    def run(self) -> None:
        try:
            text = self._fn() or ""
        except Exception:
            text = ""
        self.done.emit(text[:EXCERPT_CHARS])


class ResourceSheet(Sheet):
    """'Add Resource' / 'Edit Resource' sheet with AI-assisted tagging."""

    saved = Signal(str)
    settings_requested = Signal()

    def __init__(self, host: QWidget, library, settings, parent: QWidget | None = None) -> None:
        super().__init__(host, "Add Resource", 560)
        self._lib = library
        self._settings = settings
        self._edit: Resource | None = None
        self._queue: list[Path] = []
        self._advance = False
        self._last_module: str | None = None
        self._auto_title = ""
        self._suggested_module: str | None = None
        self._run = 0
        self._busy = False
        self._applying = False
        self._badges: dict[str, SparkleBadge] = {}
        self._build()
        self.set_title("Add Resource", _SUBTITLE)
        self.closed.connect(self._on_closed)

    # ------------------------------------------------------------------ public API
    def open_add(self, module_id: str | None = None, files: list[Path] | None = None) -> None:
        paths = [Path(f) for f in (files or []) if f and Path(f).is_file()]
        self._advance = False
        self._prepare(None, module_id)
        self._queue = paths[1:]
        if paths:
            self._drop.set_path(paths[0])
        self._update_queue_note()
        self.open()

    def open_edit(self, resource_id: str) -> None:
        r = self._lib.resource(resource_id)
        if r is None:
            return
        self._advance = False
        self._queue = []
        self._prepare(r, r.module_id)
        self._update_queue_note()
        self.open()

    # ------------------------------------------------------------------ building
    def _build(self) -> None:
        b = self.body_layout
        self._drop = DropZone()
        self._drop.file_changed.connect(self._on_file_changed)
        b.addWidget(self._drop)
        self._queue_note = StatusLabel()
        b.addWidget(self._queue_note)

        ai = QHBoxLayout()
        ai.setContentsMargins(0, 2, 0, 2)
        ai.setSpacing(10)
        self._ai_btn = make_button("Suggest Tags with AI")
        self._ai_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._ai_btn.clicked.connect(self._suggest)
        on_theme_change(self._ai_btn, lambda: self._ai_btn.setIcon(
            icons.make_icon("sparkles", system_color("purple") if self._ai_btn.isEnabled() else
                            palette().tertiary_label, 15)))
        ai.addWidget(self._ai_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._ai_spin = ActivityIndicator(16)
        ai.addWidget(self._ai_spin, 0, Qt.AlignmentFlag.AlignVCenter)
        self._ai_status = StatusLabel()
        ai.addWidget(self._ai_status, 1, Qt.AlignmentFlag.AlignVCenter)
        ai.addStretch(0)
        self._ai_settings = make_button("Settings\u2026", "plain")
        self._ai_settings.clicked.connect(self.settings_requested)
        self._ai_settings.hide()
        ai.addWidget(self._ai_settings, 0, Qt.AlignmentFlag.AlignVCenter)
        b.addLayout(ai)

        self._key_box = GroupBox()
        key_ctrl = QHBoxLayout()
        key_ctrl.setSpacing(8)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("Paste your Gemini API key")
        self._key_edit.setFont(font("body"))
        self._key_edit.setMinimumWidth(220)
        self._key_edit.installEventFilter(self)
        key_ctrl.addWidget(self._key_edit, 1)
        key_save = make_button("Save")
        key_save.clicked.connect(self._save_key)
        key_ctrl.addWidget(key_save)
        row = self._key_box.add_row("API Key", key_ctrl, icon="key", icon_color=system_color("purple"))
        tint_badges(row, "purple")
        fit_row(row)
        foot = QHBoxLayout()
        foot.setSpacing(8)
        note = QLabel("Gemini suggests the module, topic and keywords. Your key stays on this computer.")
        note.setFont(font("subheadline"))
        note.setWordWrap(True)
        on_theme_change(note, lambda: note.setStyleSheet(f"color: {rgba(palette().secondary_label)};"))
        foot.addWidget(note, 1)
        get_key = make_button("Get a Free Key\u2026", "plain")
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(API_KEY_URL)))
        foot.addWidget(get_key, 0, Qt.AlignmentFlag.AlignVCenter)
        self._key_box.add_row(None, foot)
        self._key_box.hide()
        b.addWidget(self._key_box)

        form = GroupBox()
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Title")
        self._title_edit.setFont(font("body"))
        self._title_edit.setMinimumWidth(280)
        self._title_edit.textEdited.connect(lambda _t: self._user_edit("title"))
        self._kind = KindCombo(280)
        self._kind.currentIndexChanged.connect(lambda _i: self._user_edit("kind"))
        self._module = ModuleCombo(280)
        self._module.currentIndexChanged.connect(self._on_module_changed)
        self._topic = TopicCombo(280)
        self._topic.currentIndexChanged.connect(lambda _i: self._user_edit("topic"))
        rows = {
            "title": form.add_row("Title", self._title_edit),
            "kind": form.add_row("Type", self._kind),
            "module": form.add_row("Module", self._module),
            "topic": form.add_row("Topic", self._topic),
        }
        b.addWidget(form)

        details = GroupBox()
        self._keywords = TokenField(placeholder="Add keywords (press Return after each)")
        self._keywords.changed.connect(self._on_keywords_changed)
        self._desc = QPlainTextEdit()
        self._desc.setFont(font("body"))
        self._desc.setPlaceholderText("What\u2019s in this file and how interns should use it (optional)")
        self._desc.setTabChangesFocus(True)
        self._desc.setFixedHeight(QFontMetrics(font("body")).lineSpacing() * 3 + 22)
        self._desc.textChanged.connect(lambda: self._user_edit("description"))
        self._uploader = QLineEdit()
        self._uploader.setFont(font("body"))
        self._uploader.setPlaceholderText("Your name")
        self._uploader.setMinimumWidth(280)
        rows["keywords"] = details.add_row("Keywords", self._keywords, stacked=True)
        rows["description"] = details.add_row("Description", self._desc, stacked=True)
        rows["uploader"] = details.add_row("Uploaded By", self._uploader)
        b.addWidget(details)

        for key in ("title", "kind", "module", "topic"):
            fit_row(rows[key])
        fit_row(rows["uploader"])
        for key in ("title", "kind", "module", "topic", "keywords", "description"):
            badge = SparkleBadge()
            add_label_accessory(rows[key], badge)
            self._badges[key] = badge

        self._error = StatusLabel()
        b.addWidget(self._error)

        self._save, _cancel = self.add_footer_buttons("Add Resource")
        self._save.clicked.connect(self._submit)

    # ------------------------------------------------------------------ state
    def _prepare(self, edit: Resource | None, module_id: str | None) -> None:
        self._run += 1
        self._edit = edit
        self._suggested_module = None
        self._auto_title = ""
        self._applying = True
        self._module.set_modules(self._lib.modules(), module_id)
        self._topic.set_module(self._lib.module(self._module.module_id()), edit.topic_id if edit else None)
        self._keywords.set_completions(self._lib.all_keywords())
        if edit is not None:
            self.set_title("Edit Resource", _SUBTITLE)
            self._drop.set_existing(edit.filename, edit.size, edit.ext)
            self._drop.set_clearable(False)
            self._title_edit.setText(edit.title)
            self._kind.set_kind(edit.kind)
            self._keywords.set_tokens(edit.keywords)
            self._desc.setPlainText(edit.description)
            self._uploader.setText(edit.uploader)
            self._uploader.setEnabled(False)
            self._uploader.setToolTip("The uploader can\u2019t be changed after adding.")
            self._save.setText("Save")
        else:
            self.set_title("Add Resource", _SUBTITLE)
            self._drop.set_existing(None)
            self._drop.set_clearable(True)
            self._drop.set_path(None)
            self._title_edit.clear()
            self._kind.set_kind("notes")
            self._keywords.set_tokens([])
            self._desc.clear()
            self._uploader.setText(self._settings.user_name())
            self._uploader.setEnabled(True)
            self._uploader.setToolTip("")
            self._save.setText("Add Resource")
        for badge in self._badges.values():
            badge.hide()
        self._key_box.hide()
        self._key_edit.clear()
        self._ai_settings.hide()
        self._ai_status.clear()
        self._error.clear()
        self._set_busy(False)
        self._applying = False
        self._validate()

    def on_open(self) -> None:
        if self._drop.has_file():
            QTimer.singleShot(0, lambda: (self._title_edit.setFocus(), self._title_edit.end(False)))

    def _update_queue_note(self) -> None:
        n = len(self._queue)
        if n:
            self._queue_note.set_status(f"{n} more file{'s' if n != 1 else ''} will be added next.")
        else:
            self._queue_note.clear()

    def _validate(self) -> None:
        self._save.setEnabled(self._drop.has_file() and self._module.module_id() is not None)
        self._ai_btn.setEnabled(not self._busy and self._ai_source() is not None)
        self._ai_btn.setIcon(icons.make_icon(
            "sparkles", system_color("purple") if self._ai_btn.isEnabled() else palette().tertiary_label, 15))

    def _relayout(self) -> None:
        self.relayout()

    def _user_edit(self, field: str) -> None:
        if self._applying:
            return
        badge = self._badges.get(field)
        if badge is not None:
            badge.hide()
        if field == "module":
            self._suggested_module = None

    # ------------------------------------------------------------------ field events
    def _on_file_changed(self, path) -> None:
        if self._edit is None:
            current = self._title_edit.text().strip()
            if path is not None:
                stem = prettify_stem(Path(path).stem)
                if not current or current == self._auto_title:
                    self._title_edit.setText(stem)
                    self._auto_title = stem
            elif current and current == self._auto_title:
                self._title_edit.clear()
                self._auto_title = ""
        self._error.clear()
        self._validate()
        self._relayout()

    def _on_module_changed(self, _index: int) -> None:
        module = self._lib.module(self._module.module_id())
        self._topic.set_module(module)
        if not self._applying:
            self._user_edit("module")
            self._user_edit("topic")
        self._validate()

    def _on_keywords_changed(self) -> None:
        self._user_edit("keywords")
        self._relayout()

    def eventFilter(self, obj, event):
        if obj is self._key_edit and event.type() == QEvent.Type.KeyPress \
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._save_key()
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ AI suggestions
    def _ai_source(self) -> Path | None:
        if self._drop.path() is not None:
            return self._drop.path()
        if self._edit is not None:
            try:
                p = self._lib.file_path(self._edit)
            except Exception:
                return None
            return p if p.exists() else None
        return None

    def _set_busy(self, on: bool, text: str = "") -> None:
        self._busy = on
        if on:
            self._ai_spin.start()
            self._ai_status.set_status(text)
            self._ai_settings.hide()
        else:
            self._ai_spin.stop()
        self._validate()

    def _save_key(self) -> None:
        key = self._key_edit.text().strip()
        if not key:
            self._key_edit.setFocus()
            return
        try:
            self._settings.set_api_key(key)
        except Exception as exc:
            self._ai_status.set_status(f"Couldn\u2019t save the key: {exc}", "error")
            return
        self._key_edit.clear()
        self._key_box.hide()
        self._relayout()
        self._suggest()

    def _suggest(self) -> None:
        source = self._ai_source()
        if source is None or self._busy:
            return
        key = self._settings.api_key()
        if not key:
            self._key_box.show()
            self._ai_status.set_status("Add a Gemini API key to get suggestions.")
            self._relayout()
            self._key_edit.setFocus()
            return
        try:
            from ..core.ai import SuggestWorker  # noqa: F401
        except Exception:
            self._show_ai_error("AI suggestions aren\u2019t available right now.")
            return
        self._key_box.hide()
        self._run += 1
        edit, new_path = self._edit, self._drop.path()
        if new_path is None and edit is not None:
            fn = lambda: self._lib.content_text(edit)[:EXCERPT_CHARS]  # noqa: E731
        else:
            fn = lambda: _extract_excerpt(source)  # noqa: E731
        job = _TextJob(fn, self._run, source)
        job.done.connect(self._on_text_ready)
        keep_thread(job)
        self._set_busy(True, "Reading the file\u2026")
        self._relayout()
        job.start()

    def _on_text_ready(self, text: str) -> None:
        job = self.sender()
        if getattr(job, "run_id", -1) != self._run or not self.isVisible():
            return
        try:
            from ..core.ai import SuggestWorker
            worker = SuggestWorker(
                self._settings.api_key(), self._settings.model(), self._lib.modules(), job.source,
                title=self._title_edit.text().strip(), description=self._desc.toPlainText().strip(),
                text_excerpt=text, known_keywords=self._lib.all_keywords()[:300])
        except Exception as exc:
            self._set_busy(False)
            self._show_ai_error(f"Couldn\u2019t start the suggestion: {exc}")
            return
        worker.run_id = self._run
        worker.suggested.connect(self._on_suggested)
        worker.failed.connect(self._on_failed)
        keep_thread(worker)
        self._ai_status.set_status("Asking Gemini\u2026")
        worker.start()

    def _on_suggested(self, suggestion) -> None:
        if getattr(self.sender(), "run_id", -1) != self._run or not self.isVisible():
            return
        self._set_busy(False)
        try:
            self._apply_suggestion(suggestion)
        except Exception as exc:
            self._show_ai_error(f"Couldn\u2019t use the suggestion: {exc}")
        self._relayout()

    def _on_failed(self, message: str) -> None:
        if getattr(self.sender(), "run_id", -1) != self._run or not self.isVisible():
            return
        self._set_busy(False)
        self._show_ai_error(message or "Gemini couldn\u2019t suggest tags for this file.")

    def _show_ai_error(self, message: str) -> None:
        self._ai_status.set_status(message, "error")
        self._ai_settings.show()
        self._relayout()

    def _apply_suggestion(self, s: Suggestion) -> None:
        filled: set[str] = set()
        self._applying = True
        try:
            if s.module_id and self._lib.module(s.module_id) is not None:
                self._module.set_module_id(s.module_id)
                self._topic.set_module(self._lib.module(s.module_id))
                self._suggested_module = s.module_id
                filled.add("module")
            module = self._lib.module(self._module.module_id())
            if s.topic_id and module is not None and module.topic(s.topic_id) is not None:
                self._topic.set_topic_id(s.topic_id)
                filled.add("topic")
            before = self._keywords.tokens()
            merged = merge_keywords(before, s.keywords or [])
            if len(merged) > len(before):
                self._keywords.set_tokens(merged)
                filled.add("keywords")
            if s.kind in KIND_NAMES:
                if s.kind != self._kind.kind():
                    filled.add("kind")
                self._kind.set_kind(s.kind)
            current = self._title_edit.text().strip()
            if s.title and s.title.strip() and (not current or current == self._auto_title):
                self._title_edit.setText(s.title.strip())
                self._auto_title = ""
                filled.add("title")
            if s.description and s.description.strip() and not self._desc.toPlainText().strip():
                self._desc.setPlainText(s.description.strip())
                filled.add("description")
        finally:
            self._applying = False
        for key, badge in self._badges.items():
            badge.setVisible(key in filled)
        self._validate()
        if not filled:
            self._ai_status.set_status("Gemini didn\u2019t find a better match. Choose the module and keywords "
                                       "yourself.")
            return
        pct = int(round(max(0.0, min(1.0, float(s.confidence or 0))) * 100))
        reason = (s.reason or "").strip()
        if reason and reason[-1] not in ".!?":
            reason += "."
        confidence = f" ({pct}% confident)" if pct else ""
        note = f"Suggested by Gemini{confidence}. Review before saving."
        self._ai_status.set_status(f"{reason} {note}" if reason else note, "ai")

    # ------------------------------------------------------------------ saving
    def _submit(self) -> None:
        if not self._save.isEnabled():
            return
        self._keywords.commit_pending()
        module_id = self._module.module_id()
        topic_id = self._topic.topic_id()
        title = self._title_edit.text().strip()
        kind = self._kind.kind()
        desc = self._desc.toPlainText().strip()
        keywords = self._keywords.tokens()
        ai = bool(self._suggested_module) and module_id == self._suggested_module
        self._error.clear()
        try:
            if self._edit is not None:
                r = self._lib.update_resource(
                    self._edit.id, title=title, module_id=module_id, topic_id=topic_id, kind=kind,
                    description=desc, keywords=keywords, replace_file=self._drop.path(),
                    ai_suggested=True if ai else None)
            else:
                path = self._drop.path()
                if path is None:
                    raise LibraryError("Choose a file to add.")
                r = self._lib.add_resource(path, title or prettify_stem(path.stem), module_id, topic_id, kind,
                                           desc, keywords, self._uploader.text().strip(), ai)
        except LibraryError as exc:
            self._show_error(str(exc))
            return
        except OSError as exc:
            self._show_error(f"The file couldn\u2019t be copied into the library ({exc.strerror or exc}).")
            return
        except Exception as exc:
            self._show_error(f"Couldn\u2019t save the resource: {exc}")
            return
        self._last_module = module_id
        self._advance = self._edit is None and bool(self._queue)
        self.saved.emit(r.id)
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error.set_status(message, "error")
        self._relayout()

    def _on_closed(self) -> None:
        self._run += 1
        self._busy = False
        self._ai_spin.stop()
        if self._advance and self._queue:
            pending = list(self._queue)
            module_id = self._last_module
            self._advance = False
            QTimer.singleShot(60, lambda: self.open_add(module_id, pending))
        else:
            self._queue = []
