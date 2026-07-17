"""
SQLite storage.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import config

SCHEMA_VERSION = 1

STATUS_NEW = "new"
STATUS_STARRED = "starred"
STATUS_POSTED = "posted"
STATUS_KILLED = "killed"

ALL_STATUSES = (STATUS_NEW, STATUS_STARRED, STATUS_POSTED, STATUS_KILLED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feeds (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    enabled     INTEGER NOT NULL DEFAULT 1,
    etag        TEXT,
    modified    TEXT,
    last_fetch  TEXT,
    last_status TEXT
);

CREATE TABLE IF NOT EXISTS clusters (
    id          INTEGER PRIMARY KEY,
    key_title   TEXT NOT NULL,
    norm_title  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',
    category    TEXT,
    notes       TEXT,
    posted_at   TEXT,
    posted_note TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY,
    feed_id       INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    cluster_id    INTEGER REFERENCES clusters(id) ON DELETE SET NULL,
    guid          TEXT NOT NULL,
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT,
    author        TEXT,
    published     TEXT,
    fetched_at    TEXT NOT NULL,
    UNIQUE(feed_id, guid)
);

CREATE TABLE IF NOT EXISTS templates (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    format     TEXT NOT NULL DEFAULT 'bbcode',
    kind       TEXT NOT NULL DEFAULT 'single',
    title      TEXT NOT NULL DEFAULT '',
    item       TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL,
    builtin    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_canon   ON articles(canonical_url);
CREATE INDEX IF NOT EXISTS idx_clusters_status  ON clusters(status);
CREATE INDEX IF NOT EXISTS idx_clusters_updated ON clusters(updated_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin wrapper over sqlite3. One instance per thread."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else config.db_path()
        self.conn = sqlite3.connect(str(self.path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------------------------------------------------------------- schema

    def _migrate(self) -> None:
        self.conn.executescript(SCHEMA)
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        self.conn.commit()

    # When a future version changes the schema, add the upgrade here and bump
    # SCHEMA_VERSION. One thing worth knowing before you do: read PRAGMA
    # table_info and act on the columns that are really there. Do not trust the
    # recorded version on its own. CREATE TABLE IF NOT EXISTS skips a table that
    # already exists, so a database can sit a version behind while its version
    # number claims otherwise, and every template then breaks on a column that
    # was never added.

    def seed_if_empty(self) -> None:
        """Load default feeds and templates on a fresh database."""
        from .defaults import DEFAULT_FEEDS, DEFAULT_TEMPLATES

        if self.conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0] == 0:
            for name, url in DEFAULT_FEEDS:
                self.add_feed(name, url)
        if self.conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0] == 0:
            for name, fmt, kind, title, item, body in DEFAULT_TEMPLATES:
                self.conn.execute(
                    "INSERT INTO templates(name, format, kind, title, item, body, builtin)"
                    " VALUES(?,?,?,?,?,?,1)",
                    (name, fmt, kind, title, item, body),
                )
            self.conn.commit()

    # ----------------------------------------------------------------- feeds

    def add_feed(self, name: str, url: str) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO feeds(name, url) VALUES(?, ?)", (name.strip(), url.strip())
        )
        self.conn.commit()
        if cur.lastrowid:
            return int(cur.lastrowid)
        row = self.conn.execute("SELECT id FROM feeds WHERE url=?", (url.strip(),)).fetchone()
        return int(row["id"])

    def update_feed(self, feed_id: int, name: str, url: str, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE feeds SET name=?, url=?, enabled=? WHERE id=?",
            (name.strip(), url.strip(), 1 if enabled else 0, feed_id),
        )
        self.conn.commit()

    def delete_feed(self, feed_id: int) -> None:
        self.conn.execute("DELETE FROM feeds WHERE id=?", (feed_id,))
        self.conn.commit()

    def move_feed(self, feed_id: int, new_url: str) -> None:
        """Follow a permanent redirect once instead of every refresh."""
        existing = self.conn.execute(
            "SELECT id FROM feeds WHERE url=? AND id<>?", (new_url, feed_id)
        ).fetchone()
        if existing is not None:
            return  # another feed already points there; leave this one alone
        self.conn.execute(
            "UPDATE feeds SET url=?, etag=NULL, modified=NULL WHERE id=?",
            (new_url, feed_id),
        )
        self.conn.commit()

    def set_feed_enabled(self, feed_id: int, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE feeds SET enabled=? WHERE id=?", (1 if enabled else 0, feed_id)
        )
        self.conn.commit()

    def feeds(self, only_enabled: bool = False) -> List[sqlite3.Row]:
        sql = "SELECT * FROM feeds"
        if only_enabled:
            sql += " WHERE enabled=1"
        sql += " ORDER BY name COLLATE NOCASE"
        return list(self.conn.execute(sql))

    def record_fetch(
        self,
        feed_id: int,
        status: str,
        etag: Optional[str] = None,
        modified: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            "UPDATE feeds SET last_fetch=?, last_status=?, etag=?, modified=? WHERE id=?",
            (utc_now(), status, etag, modified, feed_id),
        )
        self.conn.commit()

    # -------------------------------------------------------------- articles

    def article_exists(self, feed_id: int, guid: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM articles WHERE feed_id=? AND guid=?", (feed_id, guid)
        ).fetchone()
        return row is not None

    def cluster_for_canonical(self, canonical_url: str) -> Optional[int]:
        """Exact URL match wins over any fuzzy title comparison."""
        row = self.conn.execute(
            "SELECT cluster_id FROM articles WHERE canonical_url=? AND cluster_id IS NOT NULL"
            " ORDER BY id LIMIT 1",
            (canonical_url,),
        ).fetchone()
        return int(row["cluster_id"]) if row else None

    def insert_article(self, article: Dict[str, Any], cluster_id: int) -> Optional[int]:
        try:
            cur = self.conn.execute(
                """INSERT INTO articles
                   (feed_id, cluster_id, guid, url, canonical_url, title, summary,
                    author, published, fetched_at)
                   VALUES (:feed_id, :cluster_id, :guid, :url, :canonical_url, :title,
                           :summary, :author, :published, :fetched_at)""",
                {**article, "cluster_id": cluster_id, "fetched_at": utc_now()},
            )
        except sqlite3.IntegrityError:
            return None
        return int(cur.lastrowid) if cur.lastrowid else None

    def articles_for_cluster(self, cluster_id: int) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """SELECT a.*, f.name AS feed_name
                   FROM articles a JOIN feeds f ON f.id = a.feed_id
                   WHERE a.cluster_id=?
                   ORDER BY a.published IS NULL, a.published ASC, a.id ASC""",
                (cluster_id,),
            )
        )

    # -------------------------------------------------------------- clusters

    def recent_clusters(self, days: int) -> List[sqlite3.Row]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        return list(
            self.conn.execute(
                "SELECT id, norm_title FROM clusters WHERE updated_at >= ?", (cutoff,)
            )
        )

    def create_cluster(self, title: str, norm_title: str, category: Optional[str]) -> int:
        now = utc_now()
        cur = self.conn.execute(
            """INSERT INTO clusters(key_title, norm_title, created_at, updated_at, category)
               VALUES(?,?,?,?,?)""",
            (title, norm_title, now, now, category),
        )
        return int(cur.lastrowid)

    def touch_cluster(self, cluster_id: int) -> None:
        self.conn.execute(
            "UPDATE clusters SET updated_at=? WHERE id=?", (utc_now(), cluster_id)
        )

    def set_cluster_status(self, cluster_id: int, status: str, note: str = "") -> None:
        if status not in ALL_STATUSES:
            raise ValueError(f"unknown status: {status}")
        if status == STATUS_POSTED:
            self.conn.execute(
                "UPDATE clusters SET status=?, posted_at=?, posted_note=? WHERE id=?",
                (status, utc_now(), note, cluster_id),
            )
        else:
            self.conn.execute(
                "UPDATE clusters SET status=?, posted_at=NULL WHERE id=?", (status, cluster_id)
            )
        self.conn.commit()

    def set_cluster_category(self, cluster_id: int, category: Optional[str]) -> None:
        self.conn.execute(
            "UPDATE clusters SET category=? WHERE id=?", (category, cluster_id)
        )
        self.conn.commit()

    def set_cluster_notes(self, cluster_id: int, notes: str) -> None:
        self.conn.execute("UPDATE clusters SET notes=? WHERE id=?", (notes, cluster_id))
        self.conn.commit()

    def get_cluster(self, cluster_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM clusters WHERE id=?", (cluster_id,)).fetchone()

    def list_clusters(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        feed_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> List[sqlite3.Row]:
        """Clusters with source counts, newest first."""
        where: List[str] = []
        params: List[Any] = []
        if status:
            where.append("c.status = ?")
            params.append(status)
        if category:
            where.append("c.category = ?")
            params.append(category)
        if feed_id:
            where.append("EXISTS (SELECT 1 FROM articles x WHERE x.cluster_id=c.id AND x.feed_id=?)")
            params.append(feed_id)
        if search:
            where.append(
                "EXISTS (SELECT 1 FROM articles x WHERE x.cluster_id=c.id"
                " AND (x.title LIKE ? OR x.summary LIKE ?))"
            )
            like = f"%{search}%"
            params.extend([like, like])

        sql = """
            SELECT c.*,
                   COUNT(a.id) AS source_count,
                   MAX(COALESCE(a.published, a.fetched_at)) AS latest,
                   (SELECT title FROM articles WHERE cluster_id=c.id ORDER BY id LIMIT 1) AS lead_title
            FROM clusters c
            LEFT JOIN articles a ON a.cluster_id = c.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY c.id ORDER BY latest DESC LIMIT ?"
        params.append(limit)
        return list(self.conn.execute(sql, params))

    def status_counts(self) -> Dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM clusters GROUP BY status"
        )
        counts = {s: 0 for s in ALL_STATUSES}
        for row in rows:
            counts[row["status"]] = row["n"]
        return counts

    def categories_in_use(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT category FROM clusters WHERE category IS NOT NULL"
            " ORDER BY category"
        )
        return [r["category"] for r in rows]

    # ------------------------------------------------------------- templates

    def templates(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM templates ORDER BY name COLLATE NOCASE"))

    def get_template(self, name: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM templates WHERE name=?", (name,)).fetchone()

    def save_template(
        self,
        name: str,
        fmt: str,
        title: str,
        body: str,
        kind: str = "single",
        item: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO templates(name, format, kind, title, item, body, builtin)
               VALUES(?,?,?,?,?,?,0)
               ON CONFLICT(name) DO UPDATE SET
                   format=excluded.format,
                   kind=excluded.kind,
                   title=excluded.title,
                   item=excluded.item,
                   body=excluded.body""",
            (name.strip(), fmt, kind, title, item, body),
        )
        self.conn.commit()

    def delete_template(self, name: str) -> None:
        self.conn.execute("DELETE FROM templates WHERE name=?", (name,))
        self.conn.commit()

    # ------------------------------------------------------------- upkeep

    def purge_old(self, retention_days: int) -> int:
        """Delete aged articles, keeping anything starred or posted."""
        if retention_days <= 0:
            return 0
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat(timespec="seconds")
        cur = self.conn.execute(
            """DELETE FROM articles WHERE fetched_at < ? AND cluster_id IN (
                   SELECT id FROM clusters WHERE status IN ('new', 'killed'))""",
            (cutoff,),
        )
        removed = cur.rowcount
        self.conn.execute(
            "DELETE FROM clusters WHERE id NOT IN (SELECT DISTINCT cluster_id FROM articles"
            " WHERE cluster_id IS NOT NULL) AND status IN ('new', 'killed')"
        )
        self.conn.commit()
        self.conn.execute("VACUUM")
        return removed

    def commit(self) -> None:
        self.conn.commit()
