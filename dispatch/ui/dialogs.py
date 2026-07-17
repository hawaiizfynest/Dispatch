"""
Dialogs: feeds, templates, settings, about.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __author__, __org__, __version__
from ..config import DEFAULT_SETTINGS
from ..db import Database
from ..defaults import DEFAULT_FEEDS, TEMPLATE_TOKENS
from . import theme

MONO = "Consolas, Menlo, DejaVu Sans Mono"


class FeedManagerDialog(QDialog):
    """Add, edit, enable, and remove feeds."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Manage feeds")
        self.resize(820, 540)
        self.setStyleSheet(theme.STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hint = QLabel(
            "Uncheck a feed to skip it on refresh. Double-click a name or URL to edit it."
        )
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "URL", "Last fetch", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_add = QPushButton("Add feed")
        self.btn_add.setObjectName("primary")
        self.btn_edit = QPushButton("Edit")
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setObjectName("danger")
        self.btn_restore = QPushButton("Restore defaults")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_remove)
        row.addStretch()
        row.addWidget(self.btn_restore)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.btn_add.clicked.connect(self.add_feed)
        self.btn_edit.clicked.connect(self.edit_feed)
        self.btn_remove.clicked.connect(self.remove_feeds)
        self.btn_restore.clicked.connect(self.restore_defaults)
        self.tree.itemDoubleClicked.connect(lambda *_: self.edit_feed())
        self.tree.itemChanged.connect(self.on_item_changed)

        self.reload()

    def reload(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for feed in self.db.feeds():
            item = QTreeWidgetItem(
                self.tree,
                [
                    feed["name"],
                    feed["url"],
                    (feed["last_fetch"] or "")[:16].replace("T", " "),
                    feed["last_status"] or "",
                ],
            )
            item.setData(0, Qt.ItemDataRole.UserRole, feed["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked if feed["enabled"] else Qt.CheckState.Unchecked,
            )
            if feed["last_status"] == "error":
                item.setForeground(3, QColor(theme.DANGER))
                item.setToolTip(3, "Last refresh failed. Check the URL.")
        self.tree.blockSignals(False)

    def on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        feed_id = item.data(0, Qt.ItemDataRole.UserRole)
        if feed_id is None:
            return
        self.db.set_feed_enabled(feed_id, item.checkState(0) == Qt.CheckState.Checked)

    def add_feed(self) -> None:
        dialog = FeedEditDialog(parent=self)
        if not dialog.exec():
            return
        name, url = dialog.values()
        if not name or not url:
            return
        existing = [f["url"].lower() for f in self.db.feeds()]
        if url.lower() in existing:
            QMessageBox.information(self, "Already there", "That URL is already in the list.")
            return
        self.db.add_feed(name, url)
        self.reload()

    def edit_feed(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        feed_id = item.data(0, Qt.ItemDataRole.UserRole)
        dialog = FeedEditDialog(item.text(0), item.text(1), parent=self)
        if not dialog.exec():
            return
        name, url = dialog.values()
        if not name or not url:
            return
        self.db.update_feed(feed_id, name, url, item.checkState(0) == Qt.CheckState.Checked)
        self.reload()

    def remove_feeds(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        names = ", ".join(i.text(0) for i in items[:5])
        more = f" and {len(items) - 5} more" if len(items) > 5 else ""
        confirm = QMessageBox.question(
            self,
            "Remove feeds",
            f"Remove {names}{more}?\n\nStories already pulled from these feeds go too.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for item in items:
            self.db.delete_feed(item.data(0, Qt.ItemDataRole.UserRole))
        self.reload()

    def restore_defaults(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Restore defaults",
            "Add back any of the built-in feeds that are missing?\n\n"
            "Your own feeds stay. Nothing gets removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        existing = {f["url"].lower() for f in self.db.feeds()}
        added = 0
        for name, url in DEFAULT_FEEDS:
            if url.lower() not in existing:
                self.db.add_feed(name, url)
                added += 1
        self.reload()
        QMessageBox.information(self, "Restore defaults", f"Added {added} feed(s).")


class FeedEditDialog(QDialog):
    """Name and URL for one feed."""

    def __init__(self, name: str = "", url: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit feed" if name else "Add feed")
        self.resize(560, 150)
        self.setStyleSheet(theme.STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("BleepingComputer")
        self.url_edit = QLineEdit(url)
        self.url_edit.setPlaceholderText("https://www.bleepingcomputer.com/feed/")
        form.addRow("Name", self.name_edit)
        form.addRow("Feed URL", self.url_edit)
        layout.addLayout(form)

        hint = QLabel("RSS or Atom. Most outlets link theirs in the page footer.")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.url_edit.text().strip()


class TemplateEditorDialog(QDialog):
    """Edit the post templates and see which tokens exist."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_name: Optional[str] = None
        self.setWindowTitle("Manage templates")
        self.resize(1000, 620)
        self.setStyleSheet(theme.STYLESHEET)

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # left: list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Templates"))
        self.list = QListWidget()
        left_layout.addWidget(self.list, 1)
        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("New")
        self.btn_dup = QPushButton("Duplicate")
        self.btn_del = QPushButton("Delete")
        self.btn_del.setObjectName("danger")
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_dup)
        btn_row.addWidget(self.btn_del)
        left_layout.addLayout(btn_row)

        # right: editor
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.addWidget(QLabel("Format:"))
        self.format_box = QComboBox()
        for fmt in ("bbcode", "markdown", "plain", "html"):
            self.format_box.addItem(fmt)
        top.addWidget(self.format_box)
        top.addStretch()
        self.btn_save = QPushButton("Save template")
        self.btn_save.setObjectName("primary")
        top.addWidget(self.btn_save)
        right_layout.addLayout(top)

        right_layout.addWidget(QLabel("Thread title"))
        self.title_edit = QLineEdit()
        self.title_edit.setFont(QFont(MONO, 12))
        self.title_edit.setPlaceholderText("{category_tag}{title}{cve_suffix}")
        self.title_edit.setToolTip(
            "Rendered into the thread title box on the Compose tab.\n"
            "Same tokens as the body."
        )
        right_layout.addWidget(self.title_edit)

        right_layout.addWidget(QLabel("Body"))
        self.body = QTextEdit()
        self.body.setAcceptRichText(False)
        self.body.setFont(QFont(MONO, 12))
        right_layout.addWidget(self.body, 3)

        right_layout.addWidget(QLabel("Tokens"))
        self.tokens = QTreeWidget()
        self.tokens.setHeaderLabels(["Token", "What it fills in"])
        self.tokens.setRootIsDecorated(False)
        self.tokens.setAlternatingRowColors(True)
        self.tokens.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tokens.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for token, description in TEMPLATE_TOKENS:
            item = QTreeWidgetItem(self.tokens, [token, description])
            item.setFont(0, QFont(MONO, 11))
        self.tokens.setMaximumHeight(200)
        right_layout.addWidget(self.tokens, 1)

        token_hint = QLabel(
            "Double-click a token to drop it into whichever field you touched last."
        )
        token_hint.setObjectName("hint")
        right_layout.addWidget(token_hint)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 760])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close_checked)
        buttons.accepted.connect(self.close_checked)
        layout.addWidget(buttons)

        self._last_focus = self.body
        self.title_edit.installEventFilter(self)
        self.body.installEventFilter(self)

        self.list.currentItemChanged.connect(self.on_select)
        self.btn_new.clicked.connect(self.new_template)
        self.btn_dup.clicked.connect(self.duplicate_template)
        self.btn_del.clicked.connect(self.delete_template)
        self.btn_save.clicked.connect(self.save_template)
        self.tokens.itemDoubleClicked.connect(self.insert_token)

        self.reload()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and obj in (self.title_edit, self.body):
            self._last_focus = obj
        return super().eventFilter(obj, event)

    def reload(self, select: Optional[str] = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for tpl in self.db.templates():
            item = QListWidgetItem(tpl["name"])
            item.setData(Qt.ItemDataRole.UserRole, tpl["name"])
            if tpl["builtin"]:
                item.setToolTip("Built in. Editing it makes it yours.")
            self.list.addItem(item)
        self.list.blockSignals(False)

        target = select or self.current_name
        if target:
            matches = self.list.findItems(target, Qt.MatchFlag.MatchExactly)
            if matches:
                self.list.setCurrentItem(matches[0])
                return
        if self.list.count():
            self.list.setCurrentRow(0)

    def on_select(self, current: Optional[QListWidgetItem], _previous) -> None:
        if current is None:
            self.current_name = None
            self.title_edit.clear()
            self.body.clear()
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        tpl = self.db.get_template(name)
        if tpl is None:
            return
        self.current_name = name
        self.title_edit.setText(tpl["title"] or "{title}")
        self.body.setPlainText(tpl["body"])
        index = self.format_box.findText(tpl["format"])
        self.format_box.setCurrentIndex(index if index >= 0 else 0)

    def insert_token(self, item: QTreeWidgetItem, _column: int) -> None:
        """Drop the token wherever the cursor last was, title or body."""
        token = item.text(0)
        if self._last_focus is self.title_edit:
            self.title_edit.insert(token)
            self.title_edit.setFocus()
        else:
            self.body.insertPlainText(token)
            self.body.setFocus()

    def new_template(self) -> None:
        name, ok = QInputDialog.getText(self, "New template", "Name")
        if not ok or not name.strip():
            return
        name = name.strip()
        if self.db.get_template(name) is not None:
            QMessageBox.information(self, "Name taken", "A template already uses that name.")
            return
        self.db.save_template(
            name, "bbcode", "{category_tag}{title}{cve_suffix}",
            "[b]{title}[/b]\n\n{summary}\n\n{url}",
        )
        self.reload(select=name)

    def duplicate_template(self) -> None:
        if self.current_name is None:
            return
        name, ok = QInputDialog.getText(
            self, "Duplicate template", "New name", text=f"{self.current_name} copy"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if self.db.get_template(name) is not None:
            QMessageBox.information(self, "Name taken", "A template already uses that name.")
            return
        self.db.save_template(
            name, self.format_box.currentText(),
            self.title_edit.text(), self.body.toPlainText(),
        )
        self.reload(select=name)

    def delete_template(self) -> None:
        if self.current_name is None:
            return
        if self.list.count() <= 1:
            QMessageBox.information(
                self, "Keep one", "Keep at least one template so Compose has something to use."
            )
            return
        confirm = QMessageBox.question(
            self,
            "Delete template",
            f"Delete '{self.current_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_template(self.current_name)
        self.current_name = None
        self.reload()

    def save_template(self) -> None:
        if self.current_name is None:
            return
        self.db.save_template(
            self.current_name, self.format_box.currentText(),
            self.title_edit.text(), self.body.toPlainText(),
        )
        self.reload(select=self.current_name)

    def close_checked(self) -> None:
        """Warn on unsaved edits rather than dropping them silently."""
        if self.current_name is not None:
            tpl = self.db.get_template(self.current_name)
            dirty = tpl is not None and (
                tpl["body"] != self.body.toPlainText()
                or (tpl["title"] or "") != self.title_edit.text()
            )
            if dirty:
                confirm = QMessageBox.question(
                    self,
                    "Unsaved changes",
                    f"'{self.current_name}' has edits you have not saved.\n\nSave them?",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )
                if confirm == QMessageBox.StandardButton.Cancel:
                    return
                if confirm == QMessageBox.StandardButton.Save:
                    self.save_template()
        self.accept()


class SettingsDialog(QDialog):
    """Everything in config.json, with the tradeoffs spelled out."""

    def __init__(self, settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._settings = dict(settings)
        self.setWindowTitle("Settings")
        self.resize(560, 520)
        self.setStyleSheet(theme.STYLESHEET)

        layout = QVBoxLayout(self)

        # --- grouping
        group_cluster = QGroupBox("Duplicate detection")
        form_cluster = QFormLayout(group_cluster)

        self.threshold = QSpinBox()
        self.threshold.setRange(50, 100)
        self.threshold.setValue(int(self._settings.get("cluster_threshold", 82)))
        self.threshold.setToolTip(
            "How alike two headlines must be to count as the same story.\n"
            "Lower catches more duplicates and risks merging unrelated stories."
        )
        form_cluster.addRow("Match threshold", self.threshold)

        self.window_days = QSpinBox()
        self.window_days.setRange(1, 30)
        self.window_days.setSuffix(" days")
        self.window_days.setValue(int(self._settings.get("cluster_window_days", 5)))
        self.window_days.setToolTip("Only compare against stories seen this recently.")
        form_cluster.addRow("Compare window", self.window_days)

        self.auto_cat = QCheckBox("Tag new stories with a category guess")
        self.auto_cat.setChecked(bool(self._settings.get("auto_categorize", True)))
        form_cluster.addRow("", self.auto_cat)

        layout.addWidget(group_cluster)

        group_post = QGroupBox("Posting")
        form_post = QFormLayout(group_post)

        self.title_max = QSpinBox()
        self.title_max.setRange(20, 300)
        self.title_max.setValue(int(self._settings.get("title_max_chars", 100)))
        self.title_max.setToolTip(
            "The longest thread title your forum accepts.\n"
            "Dispatch counts against this and warns you past it.\n"
            "Check your board's limit; forums vary and some truncate without saying so."
        )
        form_post.addRow("Thread title limit", self.title_max)

        title_hint = QLabel("Dispatch warns past the limit. It never trims without asking.")
        title_hint.setObjectName("hint")
        title_hint.setWordWrap(True)
        form_post.addRow("", title_hint)

        layout.addWidget(group_post)

        group_fetch = QGroupBox("Fetching")
        form_fetch = QFormLayout(group_fetch)

        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(int(self._settings.get("fetch_timeout", 20)))
        form_fetch.addRow("Timeout per feed", self.timeout)

        self.workers = QSpinBox()
        self.workers.setRange(1, 16)
        self.workers.setValue(int(self._settings.get("fetch_workers", 6)))
        self.workers.setToolTip("Feeds pulled at once. Be polite to small sites.")
        form_fetch.addRow("Parallel fetches", self.workers)

        self.auto_refresh = QSpinBox()
        self.auto_refresh.setRange(0, 720)
        self.auto_refresh.setSuffix(" min")
        self.auto_refresh.setSpecialValueText("off")
        self.auto_refresh.setValue(int(self._settings.get("auto_refresh_minutes", 0)))
        self.auto_refresh.setToolTip("Refresh on a timer while the window is open. 0 turns it off.")
        form_fetch.addRow("Auto refresh", self.auto_refresh)

        self.user_agent = QLineEdit(str(self._settings.get("user_agent", "")))
        self.user_agent.setToolTip("Sent to every feed host. Some block blank or generic agents.")
        form_fetch.addRow("User-Agent", self.user_agent)

        layout.addWidget(group_fetch)

        group_keep = QGroupBox("Housekeeping")
        form_keep = QFormLayout(group_keep)

        self.retention = QSpinBox()
        self.retention.setRange(0, 3650)
        self.retention.setSuffix(" days")
        self.retention.setSpecialValueText("keep everything")
        self.retention.setValue(int(self._settings.get("retention_days", 120)))
        self.retention.setToolTip(
            "Purge removes articles older than this.\nStarred and posted stories are always kept."
        )
        form_keep.addRow("Retention", self.retention)

        layout.addWidget(group_keep)
        layout.addStretch()

        row = QHBoxLayout()
        self.btn_defaults = QPushButton("Reset to defaults")
        row.addWidget(self.btn_defaults)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.btn_defaults.clicked.connect(self.reset_defaults)

    def reset_defaults(self) -> None:
        self.threshold.setValue(DEFAULT_SETTINGS["cluster_threshold"])
        self.window_days.setValue(DEFAULT_SETTINGS["cluster_window_days"])
        self.auto_cat.setChecked(DEFAULT_SETTINGS["auto_categorize"])
        self.timeout.setValue(DEFAULT_SETTINGS["fetch_timeout"])
        self.workers.setValue(DEFAULT_SETTINGS["fetch_workers"])
        self.auto_refresh.setValue(DEFAULT_SETTINGS["auto_refresh_minutes"])
        self.user_agent.setText(DEFAULT_SETTINGS["user_agent"])
        self.retention.setValue(DEFAULT_SETTINGS["retention_days"])
        self.title_max.setValue(DEFAULT_SETTINGS["title_max_chars"])

    def result_settings(self) -> Dict[str, Any]:
        out = dict(self._settings)
        out.update(
            {
                "cluster_threshold": self.threshold.value(),
                "cluster_window_days": self.window_days.value(),
                "auto_categorize": self.auto_cat.isChecked(),
                "fetch_timeout": self.timeout.value(),
                "fetch_workers": self.workers.value(),
                "auto_refresh_minutes": self.auto_refresh.value(),
                "user_agent": self.user_agent.text().strip()
                or DEFAULT_SETTINGS["user_agent"],
                "retention_days": self.retention.value(),
                "title_max_chars": self.title_max.value(),
            }
        )
        return out


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {__app_name__}")
        self.resize(460, 300)
        self.setStyleSheet(theme.STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel(f"{__app_name__} {__version__}")
        title.setObjectName("heading")
        layout.addWidget(title)

        blurb = QLabel(
            "A reading desk for security news.\n\n"
            "Pulls your feeds, folds the same story from different outlets into one "
            "entry, and drafts a post you can edit. Copying the draft is the last thing "
            "it does. Posting is yours."
        )
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        layout.addStretch()

        credit = QLabel(f"{__author__}\n{__org__}")
        credit.setObjectName("hint")
        layout.addWidget(credit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
