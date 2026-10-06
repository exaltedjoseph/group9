"""Log / edit a classwork session (module, topic, date, notes and an optional attachment)."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QWidget

from ..core.library import LibraryError
from ..core.models import ClassworkEntry
from ..theme import font
from .forms import AttachmentField, DateField, ModuleCombo, StatusLabel, TopicCombo, fit_row
from .sheet import GroupBox, Sheet

_SUBTITLE = "Record what was covered so interns can catch up."


class ClassworkSheet(Sheet):
    """'Log Classwork' / 'Edit Classwork' sheet."""

    saved = Signal(str)

    def __init__(self, host: QWidget, library, settings) -> None:
        super().__init__(host, "Log Classwork", 520)
        self._lib = library
        self._settings = settings
        self._edit: ClassworkEntry | None = None
        self._build()
        self.set_title("Log Classwork", _SUBTITLE)

    # ------------------------------------------------------------------ public API
    def open_add(self, module_id: str | None = None) -> None:
        self._prepare(None, module_id)
        self.open()

    def open_edit(self, entry_id: str) -> None:
        entry = self._lib.classwork_entry(entry_id)
        if entry is None:
            return
        self._prepare(entry, entry.module_id)
        self.open()

    # ------------------------------------------------------------------ building
    def _build(self) -> None:
        b = self.body_layout
        where = GroupBox()
        self._module = ModuleCombo(260)
        self._module.currentIndexChanged.connect(self._on_module_changed)
        self._topic = TopicCombo(260)
        self._date = DateField()
        self._date.setMinimumWidth(160)
        for label, control in (("Module", self._module), ("Topic", self._topic), ("Date", self._date)):
            fit_row(where.add_row(label, control))
        b.addWidget(where)

        what = GroupBox()
        self._title_edit = QLineEdit()
        self._title_edit.setFont(font("body"))
        self._title_edit.setPlaceholderText("e.g. Loops practice session")
        self._title_edit.setMinimumWidth(260)
        self._title_edit.textChanged.connect(lambda _t: self._validate())
        fit_row(what.add_row("Title", self._title_edit))
        self._desc = QPlainTextEdit()
        self._desc.setFont(font("body"))
        self._desc.setPlaceholderText("What was covered, exercises given, notes for interns\u2026")
        self._desc.setTabChangesFocus(True)
        self._desc.setFixedHeight(QFontMetrics(font("body")).lineSpacing() * 4 + 22)
        what.add_row("Description", self._desc, stacked=True)
        b.addWidget(what)

        extra = GroupBox()
        self._attachment = AttachmentField()
        self._attachment.file_changed.connect(lambda _p: self._error.clear())
        fit_row(extra.add_row("Attachment", self._attachment))
        self._facilitator = QLineEdit()
        self._facilitator.setFont(font("body"))
        self._facilitator.setPlaceholderText("Your name")
        self._facilitator.setMinimumWidth(260)
        fit_row(extra.add_row("Facilitator", self._facilitator))
        b.addWidget(extra)

        self._error = StatusLabel()
        b.addWidget(self._error)
        self._save, _cancel = self.add_footer_buttons("Log Classwork")
        self._save.clicked.connect(self._submit)

    # ------------------------------------------------------------------ state
    def _prepare(self, entry: ClassworkEntry | None, module_id: str | None) -> None:
        self._edit = entry
        self._module.set_modules(self._lib.modules(), module_id)
        self._topic.set_module(self._lib.module(self._module.module_id()), entry.topic_id if entry else None)
        self._error.clear()
        if entry is not None:
            self.set_title("Edit Classwork", _SUBTITLE)
            self._date.set_date_iso(entry.date)
            self._title_edit.setText(entry.title)
            self._desc.setPlainText(entry.description)
            size = 0
            try:
                path = self._lib.attachment_path(entry)
                size = path.stat().st_size if path and path.exists() else 0
            except Exception:
                pass
            self._attachment.set_existing(entry.attachment_name, size)
            self._facilitator.setText(entry.facilitator)
            self._facilitator.setEnabled(False)
            self._facilitator.setToolTip("The facilitator can\u2019t be changed after logging.")
            self._save.setText("Save")
        else:
            self.set_title("Log Classwork", _SUBTITLE)
            self._date.set_date_iso("")
            self._title_edit.clear()
            self._desc.clear()
            self._attachment.set_existing(None)
            self._facilitator.setText(self._settings.user_name())
            self._facilitator.setEnabled(True)
            self._facilitator.setToolTip("")
            self._save.setText("Log Classwork")
        self._validate()

    def on_open(self) -> None:
        QTimer.singleShot(0, lambda: (self._title_edit if self._module.module_id() else self._module).setFocus())

    def _on_module_changed(self, _index: int) -> None:
        self._topic.set_module(self._lib.module(self._module.module_id()))
        self._validate()

    def _validate(self) -> None:
        self._save.setEnabled(self._module.module_id() is not None and bool(self._title_edit.text().strip()))

    # ------------------------------------------------------------------ saving
    def _submit(self) -> None:
        if not self._save.isEnabled():
            return
        module_id = self._module.module_id()
        topic_id = self._topic.topic_id()
        date = self._date.date_iso()
        title = self._title_edit.text().strip()
        desc = self._desc.toPlainText().strip()
        attachment = self._attachment.path()
        self._error.clear()
        try:
            if self._edit is not None:
                entry = self._lib.update_classwork(
                    self._edit.id, module_id=module_id, topic_id=topic_id, date=date, title=title,
                    description=desc, attachment=attachment,
                    remove_attachment=self._attachment.removed_existing() and attachment is None)
            else:
                entry = self._lib.add_classwork(module_id, date, title, desc, topic_id,
                                                self._facilitator.text().strip(), attachment)
        except LibraryError as exc:
            self._show_error(str(exc))
            return
        except OSError as exc:
            self._show_error(f"The attachment couldn\u2019t be copied into the library ({exc.strerror or exc}).")
            return
        except Exception as exc:
            self._show_error(f"Couldn\u2019t save the classwork: {exc}")
            return
        self.saved.emit(entry.id)
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error.set_status(message, "error")
        self.relayout()
