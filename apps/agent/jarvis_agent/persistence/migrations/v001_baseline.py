"""Frozen V1 baseline; applied only to a verified empty database.

Schema copied from db.py blob e2832f9f689bd2d7cf2c2ebdc617e274d3a04030.
A complete legacy database is adopted without executing these statements.
Published migration versions must never be edited.
"""

STATEMENTS = (
    """CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL
    );""",
    """CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );""",
    """CREATE TABLE tool_runs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        tool_input TEXT NOT NULL,
        result TEXT,
        error TEXT,
        success INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );""",
    """CREATE TABLE approvals (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        tool_input TEXT NOT NULL,
        status TEXT NOT NULL,
        decision TEXT,
        requested_at TEXT NOT NULL,
        decided_at TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );""",
    """CREATE TABLE memory_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        content TEXT NOT NULL,
        importance REAL NOT NULL DEFAULT 0.5,
        created_at TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
    );""",
    """CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );""",
    """CREATE TABLE allowed_paths (
        path TEXT PRIMARY KEY
    );""",
    """CREATE TABLE smarthome_entities (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        name TEXT NOT NULL,
        state TEXT NOT NULL,
        attributes TEXT NOT NULL
    );""",
    """CREATE TABLE learned_commands (
        trigger TEXT PRIMARY KEY,
        tool_name TEXT NOT NULL,
        tool_input TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        usage_count INTEGER NOT NULL DEFAULT 0,
        success_count INTEGER NOT NULL DEFAULT 0,
        failure_count INTEGER NOT NULL DEFAULT 0
    );""",
    """CREATE TABLE tool_learning_stats (
        tool_name TEXT PRIMARY KEY,
        success_count INTEGER NOT NULL DEFAULT 0,
        failure_count INTEGER NOT NULL DEFAULT 0,
        average_latency_ms REAL NOT NULL DEFAULT 0,
        last_latency_ms INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT
    );""",
    """CREATE VIRTUAL TABLE memory_items_fts
    USING fts5(content, content='memory_items', content_rowid='id');""",
    """CREATE TRIGGER memory_items_ai AFTER INSERT ON memory_items BEGIN
        INSERT INTO memory_items_fts(rowid, content) VALUES (new.id, new.content);
    END;""",
    """CREATE TRIGGER memory_items_ad AFTER DELETE ON memory_items BEGIN
        INSERT INTO memory_items_fts(memory_items_fts, rowid, content)
        VALUES('delete', old.id, old.content);
    END;""",
    """CREATE TRIGGER memory_items_au AFTER UPDATE ON memory_items BEGIN
        INSERT INTO memory_items_fts(memory_items_fts, rowid, content)
        VALUES('delete', old.id, old.content);
        INSERT INTO memory_items_fts(rowid, content)
        VALUES (new.id, new.content);
    END;""",
)
