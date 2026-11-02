"""Explicitly saved analyses only. Connections are scoped to one operation."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


class HistoryStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, request_json TEXT NOT NULL, result_json TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, title: str, request: dict, result: dict) -> str:
        analysis_id = str(uuid4())
        # Full token preview is regenerated when reopened and need not fill the database.
        compact = {k: v for k, v in result.items() if k not in {"token_preview", "word_preview"}}
        with self.connect() as conn:
            conn.execute("INSERT INTO analyses VALUES (?, ?, ?, ?, ?)", (analysis_id, title, datetime.now(timezone.utc).isoformat(), json.dumps(request), json.dumps(compact)))
        return analysis_id

    def list(self, query: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id, title, created_at, result_json FROM analyses WHERE instr(lower(title), lower(?)) > 0 ORDER BY created_at DESC LIMIT ? OFFSET ?", (query, limit, offset)).fetchall()
        items = []
        for row in rows:
            result = json.loads(row["result_json"])
            items.append({"id": row["id"], "title": row["title"], "created_at": row["created_at"], "model": result["model"]["name"], "input_tokens": result["counting"]["input_tokens"], "cost_usd": result["scenarios"]["expected"]["total_usd"]})
        return items

    def get(self, analysis_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "title": row["title"], "created_at": row["created_at"], "request": json.loads(row["request_json"]), "result": json.loads(row["result_json"])}

    def delete(self, analysis_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute("DELETE FROM analyses WHERE id=?", (analysis_id,)).rowcount > 0
