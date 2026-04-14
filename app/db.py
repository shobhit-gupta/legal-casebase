import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "storage" / "sqlite" / "casebase.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    # Special SQLite string DSNs (":memory:", URI strings) must not be
    # wrapped in Path — they are passed directly to sqlite3.connect.
    if db_path is None:
        resolved: Path | str = DB_PATH
    elif isinstance(db_path, str) and (
        db_path == ":memory:" or db_path.startswith("file:")
    ):
        resolved = db_path  # preserve as-is
    else:
        resolved = Path(db_path)

    # Create parent directory only for real filesystem paths
    if isinstance(resolved, Path):
        resolved.parent.mkdir(parents=True, exist_ok=True)

    uri = isinstance(resolved, str) and resolved.startswith("file:")
    conn = sqlite3.connect(resolved, uri=uri)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(
    db_path: Path | str | None = None,
    schema_path: Path | str | None = None,
) -> None:
    spath = Path(schema_path) if schema_path is not None else SCHEMA_PATH
    if not spath.exists():
        raise FileNotFoundError(f"Schema file not found: {spath}")

    schema = spath.read_text(encoding="utf-8")
    with get_connection(db_path) as conn:
        conn.executescript(schema)


def main() -> None:
    init_db()
    print(f"Initialized database at {DB_PATH}")


if __name__ == "__main__":
    main()
