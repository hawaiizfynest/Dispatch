"""
Background workers.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

from typing import Any, Dict, List

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..config import USER_AGENT
from ..db import Database
from ..feeds import fetch_all, ingest


class RefreshWorker(QObject):
    """
    Fetches every enabled feed and ingests the results.

    Runs on its own QThread with its own Database handle, because sqlite3
    connections are not safe to share across threads.
    """

    progress = pyqtSignal(int, int, str)   # done, total, feed name
    finished = pyqtSignal(int, int, list)  # new articles, new clusters, errors
    failed = pyqtSignal(str)

    def __init__(self, feeds: List[Dict[str, Any]], settings: Dict[str, Any]):
        super().__init__()
        self.feeds = feeds
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        db = None
        try:
            results = fetch_all(
                self.feeds,
                user_agent=self.settings.get("user_agent", USER_AGENT),
                timeout=int(self.settings.get("fetch_timeout", 20)),
                workers=int(self.settings.get("fetch_workers", 6)),
                progress=lambda d, t, n: self.progress.emit(d, t, n),
                cancelled=lambda: self._cancelled,
            )
            if self._cancelled:
                self.finished.emit(0, 0, [])
                return

            db = Database()
            new_articles, new_clusters = ingest(
                db,
                results,
                threshold=int(self.settings.get("cluster_threshold", 82)),
                window_days=int(self.settings.get("cluster_window_days", 5)),
                auto_categorize=bool(self.settings.get("auto_categorize", True)),
            )
            errors = [
                f"{r.feed_name}: {r.error or r.status}"
                for r in results
                if r.status == "error"
            ]
            self.finished.emit(new_articles, new_clusters, errors)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if db is not None:
                db.close()


class RefreshController(QObject):
    """Owns the thread so the main window does not have to."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int, list)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: RefreshWorker | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def start(self, feeds: List[Dict[str, Any]], settings: Dict[str, Any]) -> bool:
        if self.running:
            return False

        self.thread = QThread()
        self.worker = RefreshWorker(feeds, settings)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress)
        self.worker.finished.connect(self.finished)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self._teardown)
        self.worker.failed.connect(self._teardown)
        return bool(self.thread.start() or True)

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def _teardown(self, *_: Any) -> None:
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(5000)
            self.thread.deleteLater()
        if self.worker is not None:
            self.worker.deleteLater()
        self.thread = None
        self.worker = None

    def shutdown(self) -> None:
        """Called on window close."""
        self.cancel()
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(5000)
