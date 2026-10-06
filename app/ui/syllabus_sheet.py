"""Manage the syllabus: modules (name, description, color, order) and their topics."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QDialog, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QVBoxLayout, QWidget)

from .. import icons
from ..core.library import LibraryError
from ..theme import font, palette, system_color
from .alert import AlertDialog, confirm
from .forms import ColorPicker, ListPane, RowDelegate, StatusLabel, fit_row
from .sheet import GroupBox, Sheet, section_header

_ID = Qt.ItemDataRole.UserRole
_COLOR = Qt.ItemDataRole.UserRole + 1
_NAME = Qt.ItemDataRole.UserRole + 2


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _confirm(parent: QWidget, title: str, message: str, confirm_text: str, destructive: bool = True) -> bool:
    """The standard alert; long button titles stack vertically like on macOS."""
    try:
        dlg = AlertDialog(parent, title, message, confirm_text, "Cancel", destructive)
        if QFontMetrics(font("body")).horizontalAdvance(confirm_text) + 30 > 120:
            lay = dlg.layout()
            row = lay.itemAt(lay.count() - 1).layout() if lay is not None and lay.count() else None
            if isinstance(row, QBoxLayout):
                row.setDirection(QBoxLayout.Direction.BottomToTop)
        return dlg.exec() == QDialog.DialogCode.Accepted
    except Exception:
        return confirm(parent, title, message, confirm_text, destructive=destructive)


def _unique_name(base: str, existing: list[str]) -> str:
    taken = {e.lower() for e in existing}
    if base.lower() not in taken:
        return base
    n = 2
    while f"{base} {n}".lower() in taken:
        n += 1
    return f"{base} {n}"


class _ModuleList(QListWidget):
    """Module list with drag-to-reorder; emits `reordered(module_id, new_index)`."""

    reordered = Signal(str, int)
    delete_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)

    def dropEvent(self, e):
        item = self.currentItem()
        module_id = item.data(_ID) if item is not None else None
        super().dropEvent(e)
        if module_id:
            for i in range(self.count()):
                if self.item(i).data(_ID) == module_id:
                    self.setCurrentRow(i)
                    self.reordered.emit(module_id, i)
                    break

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.viewport().update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.viewport().update()


class _TopicList(_ModuleList):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)

    def keyPressEvent(self, e):
        if self.state() != QAbstractItemView.State.EditingState and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and self.currentItem() is not None:
            self.editItem(self.currentItem())
            return
        super().keyPressEvent(e)


class SyllabusSheet(Sheet):
    """The 'Modules' sheet: two panes, changes apply immediately (each one is committed to Git)."""

    def __init__(self, host: QWidget, library) -> None:
        super().__init__(host, "Modules", 680)
        self._lib = library
        self._current: str | None = None
        self._loading = False
        self._acting = False
        self._build()
        self.set_title("Modules", "Organize the syllabus interns browse by.")
        library.changed.connect(self._on_library_changed)
        self.closed.connect(self._commit_pending)

    # ------------------------------------------------------------------ building
    def _build(self) -> None:
        b = self.body_layout
        panes = QHBoxLayout()
        panes.setSpacing(16)

        self._mods = _ModuleList()
        self._mods.setItemDelegate(RowDelegate(self._mods, self._module_glyph))
        self._mods.currentRowChanged.connect(self._on_module_selected)
        self._mods.reordered.connect(self._on_reordered)
        self._mods.delete_pressed.connect(self._delete_module)
        self._mods.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._mods.customContextMenuRequested.connect(self._module_menu)
        self._mods_pane = ListPane(self._mods, "No modules yet. Click + to add one.")
        self._mods_pane.setFixedWidth(232)
        self._mods_pane.setMinimumHeight(428)
        self._mods_pane.add_button.setToolTip("Add Module")
        self._mods_pane.remove_button.setToolTip("Delete Module")
        self._mods_pane.add_clicked.connect(self._add_module)
        self._mods_pane.remove_clicked.connect(self._delete_module)
        panes.addWidget(self._mods_pane)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.setContentsMargins(0, 0, 0, 0)
        self._form = GroupBox()
        self._name = QLineEdit()
        self._name.setFont(font("body"))
        self._name.setPlaceholderText("Module name")
        self._name.setMinimumWidth(220)
        self._name.editingFinished.connect(self._save_name)
        fit_row(self._form.add_row("Name", self._name))
        self._desc = QPlainTextEdit()
        self._desc.setFont(font("body"))
        self._desc.setPlaceholderText("A short summary for interns (optional)")
        self._desc.setTabChangesFocus(True)
        self._desc.setFixedHeight(QFontMetrics(font("body")).lineSpacing() * 2 + 22)
        self._desc.installEventFilter(self)
        self._form.add_row("Description", self._desc, stacked=True)
        self._color = ColorPicker(spacing=5)
        self._color.color_changed.connect(self._save_color)
        fit_row(self._form.add_row("Color", self._color))
        right.addWidget(self._form)

        right.addSpacing(4)
        right.addWidget(section_header("Topics"))
        self._topics = _TopicList()
        self._topics.setItemDelegate(RowDelegate(self._topics))
        self._topics.itemChanged.connect(self._on_topic_edited)
        self._topics.currentRowChanged.connect(lambda _r: self._update_buttons())
        self._topics.delete_pressed.connect(self._delete_topic)
        self._topics.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._topics.customContextMenuRequested.connect(self._topic_menu)
        self._topics_pane = ListPane(self._topics, "No topics yet. Click + to add one.")
        self._topics_pane.add_button.setToolTip("Add Topic")
        self._topics_pane.remove_button.setToolTip("Delete Topic")
        self._topics_pane.add_clicked.connect(self._add_topic)
        self._topics_pane.remove_clicked.connect(self._delete_topic)
        self._topics_pane.setMinimumHeight(150)
        right.addWidget(self._topics_pane, 1)
        self._topics_hint = StatusLabel()
        self._topics_hint.set_status("Double-click a topic to rename it.")
        right.addWidget(self._topics_hint)
        panes.addLayout(right, 1)
        b.addLayout(panes)

        self._error = StatusLabel()
        b.addWidget(self._error)
        done, _ = self.add_footer_buttons("Done", None)
        done.clicked.connect(self._done)

    def _module_glyph(self, index) -> tuple[str, object]:
        return "folder_fill", system_color(index.data(_COLOR) or "blue")

    # ------------------------------------------------------------------ loading
    def on_open(self) -> None:
        self._error.clear()
        self._reload(self._current)
        QTimer.singleShot(0, self._mods.setFocus)

    def _reload(self, select: str | None = None) -> None:
        self._loading = True
        try:
            modules = self._lib.modules()
            self._mods.clear()
            row = 0
            for i, m in enumerate(modules):
                item = QListWidgetItem(m.name)
                item.setData(_ID, m.id)
                item.setData(_COLOR, m.color)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                self._mods.addItem(item)
                if m.id == select:
                    row = i
            if modules:
                self._mods.setCurrentRow(row)
        finally:
            self._loading = False
        self._mods_pane.update_hint()
        self._load_module()

    def _load_module(self) -> None:
        item = self._mods.currentItem()
        module = self._lib.module(item.data(_ID)) if item is not None else None
        self._current = module.id if module else None
        self._loading = True
        try:
            self._name.setText(module.name if module else "")
            self._desc.setPlainText(module.description if module else "")
            self._color.set_color(module.color if module else "blue")
            self._load_topics(module)
        finally:
            self._loading = False
        self._form.setEnabled(module is not None)
        self._topics_pane.setEnabled(module is not None)
        self._update_buttons()

    def _load_topics(self, module, select: str | None = None) -> None:
        was = self._loading
        self._loading = True
        try:
            self._topics.clear()
            if module is not None:
                for t in module.topics:
                    item = QListWidgetItem(t.name)
                    item.setData(_ID, t.id)
                    item.setData(_NAME, t.name)
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                                  | Qt.ItemFlag.ItemIsEditable)
                    self._topics.addItem(item)
                    if t.id == select:
                        self._topics.setCurrentItem(item)
        finally:
            self._loading = was
        self._topics_pane.update_hint()
        self._topics_hint.setVisible(self._topics.count() > 0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self._mods_pane.remove_button.setEnabled(self._mods.currentItem() is not None)
        self._topics_pane.add_button.setEnabled(self._current is not None)
        self._topics_pane.remove_button.setEnabled(self._current is not None and self._topics.currentItem() is not None)

    def _on_library_changed(self, part: str) -> None:
        if self._acting or not self.isVisible() or part not in ("syllabus", "all"):
            return
        self._reload(self._current)

    def _on_module_selected(self, _row: int) -> None:
        if self._loading:
            return
        self._load_module()

    # ------------------------------------------------------------------ operations
    def _run(self, fn: Callable[[], object]) -> bool:
        self._acting = True
        try:
            fn()
        except LibraryError as exc:
            self._show_error(str(exc))
            return False
        except Exception as exc:
            self._show_error(f"Something went wrong: {exc}")
            return False
        finally:
            self._acting = False
        self._error.clear()
        self._relayout()
        return True

    def _show_error(self, message: str) -> None:
        self._error.set_status(message, "error")
        self._relayout()

    def _relayout(self) -> None:
        self.relayout()

    def _current_item(self) -> QListWidgetItem | None:
        return self._mods.currentItem()

    def _save_name(self) -> None:
        if self._loading or not self._current:
            return
        module = self._lib.module(self._current)
        name = self._name.text().strip()
        if module is None or name == module.name:
            return
        if self._run(lambda: self._lib.update_module(module.id, name=name)):
            item = self._current_item()
            if item is not None:
                item.setText(name)
        else:
            self._loading = True
            self._name.setText(module.name)
            self._loading = False

    def _save_desc(self) -> None:
        if self._loading or not self._current:
            return
        module = self._lib.module(self._current)
        desc = self._desc.toPlainText().strip()
        if module is None or desc == module.description:
            return
        self._run(lambda: self._lib.update_module(module.id, description=desc))

    def _save_color(self, color: str) -> None:
        if self._loading or not self._current:
            return
        module_id = self._current
        if self._run(lambda: self._lib.update_module(module_id, color=color)):
            item = self._current_item()
            if item is not None:
                item.setData(_COLOR, color)

    def _commit_pending(self) -> None:
        self._save_name()
        self._save_desc()

    def _done(self) -> None:
        self._commit_pending()
        self.accept()

    def eventFilter(self, obj, event):
        if obj is self._desc and event.type() == QEvent.Type.FocusOut:
            self._save_desc()
        return super().eventFilter(obj, event)

    # modules
    def _add_module(self) -> None:
        self._commit_pending()
        name = _unique_name("New Module", [m.name for m in self._lib.modules()])
        created = []
        if self._run(lambda: created.append(self._lib.add_module(name))):
            self._reload(created[0].id)
            self._name.setFocus()
            self._name.selectAll()

    def _delete_module(self) -> None:
        module = self._lib.module(self._current) if self._current else None
        if module is None:
            return
        n_res, n_cw = self._lib.module_usage(module.id)
        total = n_res + n_cw
        if total:
            parts = []
            if n_res:
                parts.append(_plural(n_res, "resource", "resources"))
            if n_cw:
                parts.append(_plural(n_cw, "classwork entry", "classwork entries"))
            ok = _confirm(self, f"Delete \u201c{module.name}\u201d?",
                         f"It contains {' and '.join(parts)}. They\u2019ll be deleted from the library too.",
                         f"Delete Module and Its {_plural(total, 'Item', 'Items')}", destructive=True)
        else:
            ok = _confirm(self, f"Delete \u201c{module.name}\u201d?",
                         "The module and its topics will be removed from the syllabus.", "Delete", destructive=True)
        if not ok:
            return
        row = self._mods.currentRow()
        if self._run(lambda: self._lib.delete_module(module.id, delete_contents=bool(total))):
            modules = self._lib.modules()
            nxt = modules[min(row, len(modules) - 1)].id if modules else None
            self._reload(nxt)

    def _move_module(self, delta: int) -> None:
        row = self._mods.currentRow()
        if not self._current or not (0 <= row + delta < self._mods.count()):
            return
        module_id = self._current
        if self._run(lambda: self._lib.move_module(module_id, row + delta)):
            self._reload(module_id)

    def _on_reordered(self, module_id: str, index: int) -> None:
        if not self._run(lambda: self._lib.move_module(module_id, index)):
            self._reload(module_id)

    def _module_menu(self, pos) -> None:
        item = self._mods.itemAt(pos)
        if item is None:
            return
        self._mods.setCurrentItem(item)
        row = self._mods.row(item)
        menu = QMenu(self)
        menu.setFont(font("body"))
        up = menu.addAction("Move Up")
        up.setEnabled(row > 0)
        down = menu.addAction("Move Down")
        down.setEnabled(row < self._mods.count() - 1)
        menu.addSeparator()
        delete = menu.addAction("Delete Module\u2026")
        chosen = menu.exec(self._mods.viewport().mapToGlobal(pos))
        if chosen is up:
            self._move_module(-1)
        elif chosen is down:
            self._move_module(1)
        elif chosen is delete:
            self._delete_module()

    # topics
    def _add_topic(self) -> None:
        module = self._lib.module(self._current) if self._current else None
        if module is None:
            return
        name = _unique_name("New Topic", [t.name for t in module.topics])
        created = []
        if self._run(lambda: created.append(self._lib.add_topic(module.id, name))):
            self._load_topics(self._lib.module(module.id), created[0].id)
            item = self._topics.currentItem()
            if item is not None:
                self._topics.setFocus()
                self._topics.scrollToItem(item)
                self._topics.editItem(item)

    def _on_topic_edited(self, item: QListWidgetItem) -> None:
        if self._loading or not self._current:
            return
        topic_id, old = item.data(_ID), item.data(_NAME)
        new = item.text().strip()
        if new == old:
            return
        module_id = self._current
        if self._run(lambda: self._lib.rename_topic(module_id, topic_id, new)):
            self._loading = True
            item.setData(_NAME, new)
            item.setText(new)
            self._loading = False
        else:
            self._loading = True
            item.setText(old)
            self._loading = False

    def _delete_topic(self) -> None:
        item = self._topics.currentItem()
        module = self._lib.module(self._current) if self._current else None
        if item is None or module is None:
            return
        topic_id, name = item.data(_ID), item.data(_NAME)
        try:
            used = len(self._lib.resources(module_id=module.id, topic_id=topic_id)) + \
                len(self._lib.classwork(module_id=module.id, topic_id=topic_id))
        except Exception:
            used = 0
        if used and not _confirm(self, f"Delete \u201c{name}\u201d?",
                                f"{_plural(used, 'item uses', 'items use')} this topic. "
                                f"They\u2019ll stay in {module.name} without a topic.", "Delete Topic"):
            return
        row = self._topics.currentRow()
        if self._run(lambda: self._lib.delete_topic(module.id, topic_id)):
            fresh = self._lib.module(module.id)
            nxt = fresh.topics[min(row, len(fresh.topics) - 1)].id if fresh and fresh.topics else None
            self._load_topics(fresh, nxt)

    def _topic_menu(self, pos) -> None:
        item = self._topics.itemAt(pos)
        menu = QMenu(self)
        menu.setFont(font("body"))
        add = menu.addAction(icons.make_icon("plus", palette().secondary_label, 14), "Add Topic")
        rename = delete = None
        if item is not None:
            self._topics.setCurrentItem(item)
            menu.addSeparator()
            rename = menu.addAction("Rename")
            delete = menu.addAction("Delete Topic")
        chosen = menu.exec(self._topics.viewport().mapToGlobal(pos))
        if chosen is add:
            self._add_topic()
        elif rename is not None and chosen is rename:
            self._topics.editItem(item)
        elif delete is not None and chosen is delete:
            self._delete_topic()
