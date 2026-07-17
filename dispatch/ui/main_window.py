"""
Main window.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import sqlite3
import webbrowser
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QSettings, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import __app_name__, __version__, compose, config
from ..fulltext import fetch_fulltext, is_public_domain, licence_note
from ..cluster import display_url
from ..db import (
    ALL_STATUSES, STATUS_KILLED, STATUS_NEW, STATUS_POSTED, STATUS_STARRED, Database,
)
from ..defaults import CATEGORIES
from . import theme
from .dialogs import AboutDialog, FeedManagerDialog, SettingsDialog, TemplateEditorDialog
from .workers import RefreshController

FILTER_ROLE = Qt.ItemDataRole.UserRole + 1
FILTER_VALUE_ROLE = Qt.ItemDataRole.UserRole + 2

MONO_STACK = "Consolas, Menlo, DejaVu Sans Mono"

STATUS_LABELS = {
    STATUS_NEW: "Inbox",
    STATUS_STARRED: "Starred",
    STATUS_POSTED: "Posted",
    STATUS_KILLED: "Killed",
}


def _relative(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - when
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    return when.strftime("%b %d")


class MainWindow(QMainWindow):
    def __init__(self, db: Database, settings: Dict[str, Any]):
        super().__init__()
        self.db = db
        self.settings = settings
        self.refresher = RefreshController(self)
        self.current_cluster_id: Optional[int] = None
        self.filter_status: Optional[str] = STATUS_NEW
        self.filter_category: Optional[str] = None
        self.filter_feed: Optional[int] = None
        self.search_text: str = ""
        self._draft_dirty = False
        self._fulltext: Dict[int, str] = {}

        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1440, 880)
        self.setStyleSheet(theme.STYLESHEET)

        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._connect()
        self._restore_geometry()

        self.reload_sidebar()
        self.reload_queue()
        self._setup_auto_refresh()

    # ------------------------------------------------------------- building

    def _build_actions(self) -> None:
        self.act_refresh = QAction("Refresh feeds", self)
        self.act_refresh.setShortcut(QKeySequence("F5"))
        self.act_refresh.setToolTip("Pull every enabled feed (F5)")

        self.act_star = QAction("Star", self)
        self.act_star.setShortcut(QKeySequence("Ctrl+S"))
        self.act_star.setToolTip("Worth posting (Ctrl+S)")

        self.act_kill = QAction("Kill", self)
        self.act_kill.setShortcut(QKeySequence("Del"))
        self.act_kill.setToolTip("Hide from the inbox (Del)")

        self.act_posted = QAction("Mark posted", self)
        self.act_posted.setShortcut(QKeySequence("Ctrl+D"))
        self.act_posted.setToolTip("Log that you posted this (Ctrl+D)")

        self.act_unread = QAction("Back to inbox", self)
        self.act_open = QAction("Open source", self)
        self.act_open.setShortcut(QKeySequence("Ctrl+Return"))

        self.act_copy_title = QAction("Copy thread title", self)
        self.act_copy_title.setShortcut(QKeySequence("Ctrl+Shift+T"))

        self.act_feeds = QAction("Manage feeds...", self)
        self.act_templates = QAction("Manage templates...", self)
        self.act_settings = QAction("Settings...", self)
        self.act_purge = QAction("Purge old items...", self)
        self.act_about = QAction("About", self)
        self.act_quit = QAction("Exit", self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        file_menu.addAction(self.act_refresh)
        file_menu.addSeparator()
        file_menu.addAction(self.act_settings)
        file_menu.addAction(self.act_purge)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        feeds_menu = bar.addMenu("Fee&ds")
        feeds_menu.addAction(self.act_feeds)

        tpl_menu = bar.addMenu("&Templates")
        tpl_menu.addAction(self.act_templates)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.addAction(self.act_refresh)
        tb.addSeparator()
        tb.addAction(self.act_star)
        tb.addAction(self.act_posted)
        tb.addAction(self.act_kill)
        tb.addAction(self.act_unread)
        tb.addSeparator()
        tb.addAction(self.act_open)
        tb.addAction(self.act_copy_title)

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search headlines and summaries...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedWidth(280)
        tb.addWidget(self.search_box)

    def _build_body(self) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- sidebar
        self.sidebar = QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setIndentation(12)
        self.sidebar.setMinimumWidth(180)
        self.sidebar.setMaximumWidth(320)

        # --- queue
        queue_wrap = QWidget()
        queue_layout = QVBoxLayout(queue_wrap)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(6)

        self.queue_label = QLabel("Inbox")
        self.queue_label.setObjectName("heading")
        queue_layout.addWidget(self.queue_label)

        self.queue = QTableWidget(0, 4)
        self.queue.setHorizontalHeaderLabels(["Headline", "Category", "Src", "Seen"])
        self.queue.verticalHeader().setVisible(False)
        self.queue.setAlternatingRowColors(True)
        self.queue.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue.setWordWrap(False)
        header = self.queue.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        queue_layout.addWidget(self.queue)

        # --- detail
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_sources_tab(), "Sources")
        self.tabs.addTab(self._build_compose_tab(), "Compose")

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(queue_wrap)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 4)
        self.splitter.setSizes([200, 480, 620])

        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.addWidget(self.splitter)
        self.setCentralWidget(wrap)

    def _build_sources_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.detail_title = QLabel("Nothing selected")
        self.detail_title.setObjectName("heading")
        self.detail_title.setWordWrap(True)
        layout.addWidget(self.detail_title)

        meta_row = QHBoxLayout()
        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("hint")
        meta_row.addWidget(self.detail_meta)
        meta_row.addStretch()
        meta_row.addWidget(QLabel("Category:"))
        self.category_box = QComboBox()
        self.category_box.addItem("(none)", None)
        for cat in CATEGORIES:
            self.category_box.addItem(cat, cat)
        meta_row.addWidget(self.category_box)
        layout.addLayout(meta_row)

        self.sources = QTreeWidget()
        self.sources.setHeaderLabels(["Outlet", "Headline", "Published"])
        self.sources.setRootIsDecorated(False)
        self.sources.setAlternatingRowColors(True)
        self.sources.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sources.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.sources.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.sources.setMaximumHeight(190)
        layout.addWidget(self.sources)

        layout.addWidget(QLabel("Summary"))
        self.summary_view = QTextEdit()
        self.summary_view.setReadOnly(True)
        layout.addWidget(self.summary_view, 1)

        layout.addWidget(QLabel("Your notes"))
        self.notes_box = QTextEdit()
        self.notes_box.setMaximumHeight(90)
        self.notes_box.setPlaceholderText("Angle, context, anything you want in the post...")
        layout.addWidget(self.notes_box)

        return widget

    def _build_compose_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Template:"))
        self.template_box = QComboBox()
        self.template_box.setMinimumWidth(220)
        top.addWidget(self.template_box)
        self.btn_rerender = QPushButton("Re-render")
        self.btn_rerender.setToolTip("Rebuild title and body from the template, discarding edits")
        top.addWidget(self.btn_rerender)
        top.addStretch()
        self.btn_edit_tpl = QPushButton("Edit templates...")
        top.addWidget(self.btn_edit_tpl)
        layout.addLayout(top)

        layout.addWidget(QLabel("Thread title"))
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("The thread title lands here")
        self.title_edit.setFont(QFont(MONO_STACK, 12))
        title_row.addWidget(self.title_edit, 1)
        self.title_count = QLabel("0")
        self.title_count.setMinimumWidth(58)
        self.title_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_count.setToolTip(
            "Characters in the title against your forum's limit.\n"
            "Set the limit in File > Settings."
        )
        title_row.addWidget(self.title_count)
        self.btn_trim = QPushButton("Trim")
        self.btn_trim.setToolTip("Cut the title to fit, on a word boundary")
        title_row.addWidget(self.btn_trim)
        self.btn_copy_title = QPushButton("Copy title")
        title_row.addWidget(self.btn_copy_title)
        title_row.addLayout(QHBoxLayout())
        layout.addLayout(title_row)

        source_row = QHBoxLayout()
        source_row.setSpacing(6)
        self.btn_fulltext = QPushButton("Fetch full text")
        self.btn_fulltext.setToolTip(
            "Pull the whole article in.\n"
            "Only works on US government advisories, which are public domain."
        )
        source_row.addWidget(self.btn_fulltext)
        self.licence_label = QLabel("")
        self.licence_label.setObjectName("hint")
        self.licence_label.setWordWrap(True)
        source_row.addWidget(self.licence_label, 1)
        layout.addLayout(source_row)

        layout.addWidget(QLabel("Body"))
        self.draft = QTextEdit()
        self.draft.setAcceptRichText(False)
        self.draft.setFont(QFont(MONO_STACK, 12))
        self.draft.setPlaceholderText(
            "Pick a story from the queue and the draft lands here.\n\n"
            "Edit it however you like, hit Copy body, then paste it yourself."
        )
        layout.addWidget(self.draft, 1)

        bottom = QHBoxLayout()
        self.draft_hint = QLabel("Dispatch never posts anything. You paste it.")
        self.draft_hint.setObjectName("hint")
        bottom.addWidget(self.draft_hint)
        bottom.addStretch()
        self.btn_copy = QPushButton("Copy body")
        self.btn_copy.setObjectName("primary")
        self.btn_copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.btn_copy.setToolTip("Copy the body to clipboard (Ctrl+Shift+C)")
        bottom.addWidget(self.btn_copy)
        self.btn_copy_posted = QPushButton("Copy body and mark posted")
        bottom.addWidget(self.btn_copy_posted)
        layout.addLayout(bottom)

        return widget

    def _build_statusbar(self) -> None:
        self.progress = QProgressBar()
        self.progress.setFixedWidth(190)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("Ready")

    def _connect(self) -> None:
        self.act_refresh.triggered.connect(self.refresh_feeds)
        self.act_star.triggered.connect(lambda: self.set_status(STATUS_STARRED))
        self.act_kill.triggered.connect(lambda: self.set_status(STATUS_KILLED))
        self.act_posted.triggered.connect(lambda: self.set_status(STATUS_POSTED))
        self.act_unread.triggered.connect(lambda: self.set_status(STATUS_NEW))
        self.act_open.triggered.connect(self.open_lead_source)
        self.act_copy_title.triggered.connect(self.copy_title)
        self.act_feeds.triggered.connect(self.open_feed_manager)
        self.act_templates.triggered.connect(self.open_template_editor)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_purge.triggered.connect(self.purge_old)
        self.act_about.triggered.connect(lambda: AboutDialog(self).exec())
        self.act_quit.triggered.connect(self.close)

        self.sidebar.itemClicked.connect(self.on_sidebar_click)
        self.queue.itemSelectionChanged.connect(self.on_queue_select)
        self.queue.customContextMenuRequested.connect(self.on_queue_context)
        self.queue.cellDoubleClicked.connect(lambda *_: self.open_lead_source())
        self.search_box.textChanged.connect(self.on_search)
        self.sources.itemDoubleClicked.connect(self.on_source_double_click)
        self.category_box.currentIndexChanged.connect(self.on_category_change)
        self.notes_box.textChanged.connect(self.on_notes_change)

        self.template_box.currentIndexChanged.connect(self.on_template_change)
        self.btn_rerender.clicked.connect(lambda: self.render_draft(force=True))
        self.btn_edit_tpl.clicked.connect(self.open_template_editor)
        self.btn_fulltext.clicked.connect(self.fetch_article_fulltext)
        self.btn_copy_title.clicked.connect(self.copy_title)
        self.btn_trim.clicked.connect(self.trim_title)
        self.title_edit.textChanged.connect(self.update_title_count)
        self.btn_copy.clicked.connect(lambda: self.copy_draft(mark_posted=False))
        self.btn_copy_posted.clicked.connect(lambda: self.copy_draft(mark_posted=True))
        self.draft.textChanged.connect(self._on_draft_edited)

        self.refresher.progress.connect(self.on_refresh_progress)
        self.refresher.finished.connect(self.on_refresh_finished)
        self.refresher.failed.connect(self.on_refresh_failed)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(220)
        self.search_timer.timeout.connect(self.reload_queue)

        self.notes_timer = QTimer(self)
        self.notes_timer.setSingleShot(True)
        self.notes_timer.setInterval(600)
        self.notes_timer.timeout.connect(self._save_notes)

        self.reload_templates()

    def _setup_auto_refresh(self) -> None:
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.refresh_feeds)
        minutes = int(self.settings.get("auto_refresh_minutes", 0) or 0)
        if minutes > 0:
            self.auto_timer.start(minutes * 60 * 1000)

    # -------------------------------------------------------------- sidebar

    def reload_sidebar(self) -> None:
        expanded = self._expanded_sidebar_nodes()
        self.sidebar.blockSignals(True)
        self.sidebar.clear()

        counts = self.db.status_counts()
        status_root = QTreeWidgetItem(self.sidebar, ["Queue"])
        status_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        for status in ALL_STATUSES:
            label = f"{STATUS_LABELS[status]}  ({counts.get(status, 0)})"
            item = QTreeWidgetItem(status_root, [label])
            item.setData(0, FILTER_ROLE, "status")
            item.setData(0, FILTER_VALUE_ROLE, status)
            color = theme.STATUS_COLORS.get(status)
            if color:
                item.setForeground(0, QColor(color))
        all_item = QTreeWidgetItem(status_root, ["Everything"])
        all_item.setData(0, FILTER_ROLE, "status")
        all_item.setData(0, FILTER_VALUE_ROLE, None)

        cat_root = QTreeWidgetItem(self.sidebar, ["Category"])
        cat_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        for cat in self.db.categories_in_use():
            item = QTreeWidgetItem(cat_root, [cat])
            item.setData(0, FILTER_ROLE, "category")
            item.setData(0, FILTER_VALUE_ROLE, cat)
            color = theme.CATEGORY_COLORS.get(cat)
            if color:
                item.setForeground(0, QColor(color))

        feed_root = QTreeWidgetItem(self.sidebar, ["Feeds"])
        feed_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        for feed in self.db.feeds():
            label = feed["name"]
            item = QTreeWidgetItem(feed_root, [label])
            item.setData(0, FILTER_ROLE, "feed")
            item.setData(0, FILTER_VALUE_ROLE, feed["id"])
            if not feed["enabled"]:
                item.setForeground(0, QColor(theme.TEXT_DIM))
                item.setText(0, f"{label}  (off)")
            if feed["last_status"] == "error":
                item.setForeground(0, QColor(theme.DANGER))
                item.setToolTip(0, "Last fetch failed. Open Feeds > Manage feeds.")

        for root in (status_root, cat_root, feed_root):
            root.setExpanded(root.text(0) in expanded if expanded else root is status_root)
        if not expanded:
            status_root.setExpanded(True)
            cat_root.setExpanded(True)

        self.sidebar.blockSignals(False)

    def _expanded_sidebar_nodes(self) -> set:
        out = set()
        for i in range(self.sidebar.topLevelItemCount()):
            item = self.sidebar.topLevelItem(i)
            if item.isExpanded():
                out.add(item.text(0))
        return out

    def on_sidebar_click(self, item: QTreeWidgetItem, _column: int) -> None:
        kind = item.data(0, FILTER_ROLE)
        if kind is None:
            return
        value = item.data(0, FILTER_VALUE_ROLE)
        if kind == "status":
            self.filter_status = value
            self.filter_category = None
            self.filter_feed = None
            self.queue_label.setText(STATUS_LABELS.get(value, "Everything"))
        elif kind == "category":
            self.filter_category = value
            self.filter_status = None
            self.filter_feed = None
            self.queue_label.setText(f"Category: {value}")
        elif kind == "feed":
            self.filter_feed = value
            self.filter_status = None
            self.filter_category = None
            self.queue_label.setText(f"Feed: {item.text(0)}")
        self.reload_queue()

    # ---------------------------------------------------------------- queue

    def reload_queue(self) -> None:
        keep = self.current_cluster_id
        rows = self.db.list_clusters(
            status=self.filter_status,
            category=self.filter_category,
            feed_id=self.filter_feed,
            search=self.search_text or None,
        )

        self.queue.blockSignals(True)
        self.queue.setRowCount(0)
        self.queue.setRowCount(len(rows))
        restore_row = None

        for row_index, row in enumerate(rows):
            title = row["lead_title"] or row["key_title"]
            title_item = QTableWidgetItem(title)
            title_item.setData(Qt.ItemDataRole.UserRole, row["id"])
            title_item.setToolTip(title)
            if row["status"] == STATUS_STARRED:
                font = title_item.font()
                font.setBold(True)
                title_item.setFont(font)
            elif row["status"] == STATUS_KILLED:
                title_item.setForeground(QColor(theme.TEXT_DIM))
            elif row["status"] == STATUS_POSTED:
                title_item.setForeground(QColor(theme.OK))
            self.queue.setItem(row_index, 0, title_item)

            cat = row["category"] or ""
            cat_item = QTableWidgetItem(cat)
            if cat in theme.CATEGORY_COLORS:
                cat_item.setForeground(QColor(theme.CATEGORY_COLORS[cat]))
            self.queue.setItem(row_index, 1, cat_item)

            count_item = QTableWidgetItem(str(row["source_count"]))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if row["source_count"] > 1:
                count_item.setForeground(QColor(theme.ACCENT))
                count_item.setToolTip(f"{row['source_count']} outlets carried this")
            self.queue.setItem(row_index, 2, count_item)

            self.queue.setItem(row_index, 3, QTableWidgetItem(_relative(row["latest"])))

            if row["id"] == keep:
                restore_row = row_index

        self.queue.blockSignals(False)

        if restore_row is not None:
            self.queue.selectRow(restore_row)
        elif rows:
            self.queue.selectRow(0)
        else:
            self.current_cluster_id = None
            self.clear_detail()

        self.statusBar().showMessage(f"{len(rows)} stories")

    def selected_cluster_ids(self) -> List[int]:
        ids = []
        for index in self.queue.selectionModel().selectedRows():
            item = self.queue.item(index.row(), 0)
            if item is not None:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def on_queue_select(self) -> None:
        ids = self.selected_cluster_ids()
        if not ids:
            return
        self.current_cluster_id = ids[0]
        if len(ids) == 1:
            self.load_detail(ids[0])
        else:
            # Several rows selected: a roundup template wants all of them.
            tpl = self.db.get_template(self.template_box.currentText())
            if tpl is not None and tpl["kind"] == "digest":
                self.render_digest(tpl)
            else:
                self.load_detail(ids[0])

    def on_queue_context(self, pos) -> None:
        if not self.selected_cluster_ids():
            return
        menu = QMenu(self)
        menu.addAction(self.act_open)
        menu.addSeparator()
        menu.addAction(self.act_star)
        menu.addAction(self.act_posted)
        menu.addAction(self.act_kill)
        menu.addAction(self.act_unread)
        menu.exec(self.queue.viewport().mapToGlobal(pos))

    def on_search(self, text: str) -> None:
        self.search_text = text.strip()
        self.search_timer.start()

    # --------------------------------------------------------------- detail

    def clear_detail(self) -> None:
        self.detail_title.setText("Nothing selected")
        self.detail_meta.setText("")
        self.sources.clear()
        self.summary_view.clear()
        self.notes_box.blockSignals(True)
        self.notes_box.clear()
        self.notes_box.blockSignals(False)
        self.title_edit.blockSignals(True)
        self.title_edit.clear()
        self.title_edit.blockSignals(False)
        self.update_title_count()
        self.draft.blockSignals(True)
        self.draft.clear()
        self.draft.blockSignals(False)
        self._draft_dirty = False

    def load_detail(self, cluster_id: int) -> None:
        row = self.db.get_cluster(cluster_id)
        if row is None:
            self.clear_detail()
            return
        articles = self.db.articles_for_cluster(cluster_id)
        if not articles:
            self.clear_detail()
            return

        lead = articles[0]
        self.detail_title.setText(lead["title"])

        outlets = ", ".join(sorted({a["feed_name"] for a in articles}))
        posted = f"  ·  posted {_relative(row['posted_at'])}" if row["posted_at"] else ""
        self.detail_meta.setText(
            f"{len(articles)} source{'s' if len(articles) != 1 else ''}  ·  {outlets}"
            f"  ·  {row['status']}{posted}"
        )

        self.sources.clear()
        for article in articles:
            item = QTreeWidgetItem(
                self.sources,
                [
                    article["feed_name"],
                    article["title"],
                    (article["published"] or "")[:10],
                ],
            )
            item.setData(0, Qt.ItemDataRole.UserRole, display_url(article["url"] or ""))
            item.setToolTip(1, article["title"])
        self.sources.setCurrentItem(self.sources.topLevelItem(0))

        summary_parts = []
        for article in articles:
            if article["summary"]:
                summary_parts.append(f"[{article['feed_name']}]\n{article['summary']}")
        self.summary_view.setPlainText("\n\n".join(summary_parts) or "(no summary in feed)")

        self.category_box.blockSignals(True)
        index = self.category_box.findData(row["category"])
        self.category_box.setCurrentIndex(index if index >= 0 else 0)
        self.category_box.blockSignals(False)

        self.notes_box.blockSignals(True)
        self.notes_box.setPlainText(row["notes"] or "")
        self.notes_box.blockSignals(False)

        self._draft_dirty = False
        self.render_draft(force=True)

    def on_source_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        url = item.data(0, Qt.ItemDataRole.UserRole)
        if url:
            webbrowser.open(url)

    def open_lead_source(self) -> None:
        if self.current_cluster_id is None:
            return
        articles = self.db.articles_for_cluster(self.current_cluster_id)
        if articles:
            url = display_url(articles[0]["url"] or "")
            if url:
                webbrowser.open(url)

    def on_category_change(self, _index: int) -> None:
        if self.current_cluster_id is None:
            return
        self.db.set_cluster_category(
            self.current_cluster_id, self.category_box.currentData()
        )
        self.reload_sidebar()
        self.reload_queue()

    def on_notes_change(self) -> None:
        self.notes_timer.start()

    def _save_notes(self) -> None:
        if self.current_cluster_id is None:
            return
        self.db.set_cluster_notes(self.current_cluster_id, self.notes_box.toPlainText())

    # -------------------------------------------------------------- statuses

    def set_status(self, status: str) -> None:
        ids = self.selected_cluster_ids()
        if not ids:
            return
        for cluster_id in ids:
            self.db.set_cluster_status(cluster_id, status)
        self.reload_sidebar()
        self.reload_queue()
        verb = {
            STATUS_STARRED: "Starred",
            STATUS_KILLED: "Killed",
            STATUS_POSTED: "Marked posted",
            STATUS_NEW: "Back in inbox",
        }[status]
        self.statusBar().showMessage(f"{verb}: {len(ids)} story(s)", 4000)

    # -------------------------------------------------------------- compose

    def reload_templates(self) -> None:
        current = self.template_box.currentText() or self.settings.get("last_template", "")
        self.template_box.blockSignals(True)
        self.template_box.clear()
        for tpl in self.db.templates():
            self.template_box.addItem(tpl["name"], tpl["name"])
        index = self.template_box.findText(current)
        self.template_box.setCurrentIndex(index if index >= 0 else 0)
        self.template_box.blockSignals(False)

    def on_template_change(self, _index: int) -> None:
        self.settings["last_template"] = self.template_box.currentText()
        config.save_settings(self.settings)
        self.render_draft(force=True)

    def _on_draft_edited(self) -> None:
        self._draft_dirty = True

    def render_draft(self, force: bool = False) -> None:
        if self.current_cluster_id is None:
            return
        if self._draft_dirty and not force:
            return

        name = self.template_box.currentText()
        tpl = self.db.get_template(name)
        if tpl is None:
            return
        row = self.db.get_cluster(self.current_cluster_id)
        articles = self.db.articles_for_cluster(self.current_cluster_id)
        if row is None or not articles:
            return

        limit = int(self.settings.get("title_max_chars", 100))

        if tpl["kind"] == "digest":
            self.render_digest(tpl)
            return

        context = compose.build_context(
            row, articles, title_limit=limit,
            fulltext=self._fulltext.get(self.current_cluster_id, ""),
        )
        self.update_licence_label(articles)

        title = compose.render_title(tpl["title"] or "{title}", context)
        self.title_edit.blockSignals(True)
        self.title_edit.setText(title)
        self.title_edit.blockSignals(False)
        self.update_title_count()

        text = compose.render(tpl["body"], context)
        self.draft.blockSignals(True)
        self.draft.setPlainText(text)
        self.draft.blockSignals(False)
        self._draft_dirty = False

    def render_digest(self, tpl) -> None:
        """Build one post out of every selected story."""
        ids = self.selected_cluster_ids()
        if len(ids) < 2:
            self.title_edit.blockSignals(True)
            self.title_edit.setText("")
            self.title_edit.blockSignals(False)
            self.update_title_count()
            self.draft.blockSignals(True)
            self.draft.setPlainText(
                "This is a roundup template.\n\n"
                "Select two or more stories in the queue (Ctrl+click, or Shift+click "
                "for a run) and the post builds itself from all of them."
            )
            self.draft.blockSignals(False)
            self.licence_label.setText("")
            self._draft_dirty = False
            return

        entries = []
        for cluster_id in ids:
            row = self.db.get_cluster(cluster_id)
            articles = self.db.articles_for_cluster(cluster_id)
            if row is None or not articles:
                continue
            entries.append(
                compose.build_context(
                    row, articles,
                    fulltext=self._fulltext.get(cluster_id, ""),
                )
            )
        if not entries:
            return

        notes = self.notes_box.toPlainText()
        digest_ctx = compose.build_digest_context(entries, tpl["item"], notes)
        title = compose.render_title(tpl["title"] or "{count} stories", digest_ctx)
        self.title_edit.blockSignals(True)
        self.title_edit.setText(title)
        self.title_edit.blockSignals(False)
        self.update_title_count()

        text = compose.render_digest(tpl["body"], tpl["item"], entries, notes)
        self.draft.blockSignals(True)
        self.draft.setPlainText(text)
        self.draft.blockSignals(False)
        self.licence_label.setText(f"Roundup of {len(entries)} stories.")
        self._draft_dirty = False

    def update_licence_label(self, articles) -> None:
        """Say whether full text is on the table for this source, and why."""
        if not articles:
            self.licence_label.setText("")
            self.btn_fulltext.setEnabled(False)
            return
        url = articles[0]["url"] or ""
        allowed = is_public_domain(url)
        self.btn_fulltext.setEnabled(allowed)
        note = licence_note(url)
        colour = theme.OK if allowed else theme.TEXT_DIM
        if self._fulltext.get(self.current_cluster_id):
            note = "Full text pulled in. Use {fulltext} in a template to place it."
        self.licence_label.setText(note)
        self.licence_label.setStyleSheet(f"color: {colour};")

    def fetch_article_fulltext(self) -> None:
        if self.current_cluster_id is None:
            return
        articles = self.db.articles_for_cluster(self.current_cluster_id)
        if not articles:
            return
        url = articles[0]["url"] or ""
        self.btn_fulltext.setEnabled(False)
        self.statusBar().showMessage("Fetching advisory...")
        QApplication.processEvents()

        text, status = fetch_fulltext(
            url,
            user_agent=self.settings.get("user_agent", config.USER_AGENT),
            timeout=int(self.settings.get("fetch_timeout", 20)),
        )
        self.btn_fulltext.setEnabled(True)
        self.statusBar().showMessage(status, 8000)
        if text:
            self._fulltext[self.current_cluster_id] = text
            self.render_draft(force=True)
        else:
            QMessageBox.information(self, "Full text", status)

    def update_title_count(self) -> None:
        """Colour the counter as the title approaches and passes the limit."""
        limit = int(self.settings.get("title_max_chars", 100))
        length = len(self.title_edit.text())
        self.title_count.setText(f"{length}/{limit}")
        if length > limit:
            colour = theme.DANGER
        elif length > limit * 0.9:
            colour = theme.WARN
        else:
            colour = theme.TEXT_DIM
        self.title_count.setStyleSheet(f"color: {colour};")
        self.btn_trim.setEnabled(length > limit)

    def trim_title(self) -> None:
        limit = int(self.settings.get("title_max_chars", 100))
        self.title_edit.setText(compose.trim_title(self.title_edit.text(), limit))
        self.update_title_count()

    def copy_title(self) -> None:
        text = self.title_edit.text().strip()
        if not text:
            self.statusBar().showMessage("No title to copy", 3000)
            return
        limit = int(self.settings.get("title_max_chars", 100))
        QApplication.clipboard().setText(text)
        if len(text) > limit:
            self.statusBar().showMessage(
                f"Copied, but it runs {len(text) - limit} over your {limit} limit", 6000
            )
        else:
            self.statusBar().showMessage("Title copied. Paste it into the title field.", 4000)

    def copy_draft(self, mark_posted: bool = False) -> None:
        text = self.draft.toPlainText().strip()
        if not text:
            self.statusBar().showMessage("No body to copy", 3000)
            return
        QApplication.clipboard().setText(text)
        if mark_posted and self.current_cluster_id is not None:
            self.db.set_cluster_status(self.current_cluster_id, STATUS_POSTED)
            self.reload_sidebar()
            self.reload_queue()
            self.statusBar().showMessage("Body copied. Marked posted. Paste it yourself.", 5000)
        else:
            self.statusBar().showMessage("Body copied to clipboard", 4000)

    # -------------------------------------------------------------- refresh

    def refresh_feeds(self) -> None:
        if self.refresher.running:
            self.statusBar().showMessage("Refresh already running", 3000)
            return
        feeds = [dict(f) for f in self.db.feeds(only_enabled=True)]
        if not feeds:
            QMessageBox.information(
                self, "No feeds",
                "No feeds are enabled. Open Feeds > Manage feeds and add or enable some."
            )
            return
        self.act_refresh.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(feeds))
        self.progress.setValue(0)
        self.statusBar().showMessage("Refreshing feeds...")
        self.refresher.start(feeds, self.settings)

    @pyqtSlot(int, int, str)
    def on_refresh_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.statusBar().showMessage(f"Fetched {done}/{total} — {name}")

    @pyqtSlot(int, int, list)
    def on_refresh_finished(self, new_articles: int, new_clusters: int, errors: list) -> None:
        self.act_refresh.setEnabled(True)
        self.progress.setVisible(False)
        self.reload_sidebar()
        self.reload_queue()

        msg = f"{new_articles} new article(s), {new_clusters} new story(s)"
        if errors:
            msg += f" — {len(errors)} feed(s) failed"
            self.statusBar().showMessage(msg, 9000)
            QMessageBox.warning(
                self, "Some feeds failed",
                "These feeds did not return anything:\n\n" + "\n".join(errors[:12])
                + ("\n..." if len(errors) > 12 else "")
                + "\n\nEverything else was ingested."
            )
        else:
            self.statusBar().showMessage(msg, 7000)

    @pyqtSlot(str)
    def on_refresh_failed(self, error: str) -> None:
        self.act_refresh.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Refresh failed", f"The refresh stopped:\n\n{error}")

    # --------------------------------------------------------------- dialogs

    def open_feed_manager(self) -> None:
        dialog = FeedManagerDialog(self.db, self)
        dialog.exec()
        self.reload_sidebar()
        self.reload_queue()

    def open_template_editor(self) -> None:
        dialog = TemplateEditorDialog(self.db, self)
        dialog.exec()
        self.reload_templates()
        self.render_draft(force=True)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.result_settings()
            config.save_settings(self.settings)
            self.auto_timer.stop()
            minutes = int(self.settings.get("auto_refresh_minutes", 0) or 0)
            if minutes > 0:
                self.auto_timer.start(minutes * 60 * 1000)
            self.statusBar().showMessage("Settings saved", 4000)

    def purge_old(self) -> None:
        days = int(self.settings.get("retention_days", 120))
        if days <= 0:
            QMessageBox.information(
                self, "Purge disabled",
                "Retention is set to 0 in Settings, which keeps everything."
            )
            return
        confirm = QMessageBox.question(
            self, "Purge old items",
            f"Delete articles older than {days} days?\n\n"
            "Starred and posted stories are kept no matter how old they are.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        removed = self.db.purge_old(days)
        self.reload_sidebar()
        self.reload_queue()
        self.statusBar().showMessage(f"Purged {removed} article(s)", 6000)

    # ------------------------------------------------------------- geometry

    def _restore_geometry(self) -> None:
        qs = QSettings("Colorado Vista IT Solutions", __app_name__)
        geometry = qs.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = qs.value("splitter")
        if state is not None:
            self.splitter.restoreState(state)

    def closeEvent(self, event) -> None:
        qs = QSettings("Colorado Vista IT Solutions", __app_name__)
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("splitter", self.splitter.saveState())
        self._save_notes()
        self.refresher.shutdown()
        super().closeEvent(event)
