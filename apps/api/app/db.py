import os
from contextlib import contextmanager
from typing import Any, Iterable, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Result

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/claimscope")

_engine: Optional[Engine] = None

def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, future=True)
    return _engine

@contextmanager
def session() -> Iterable[Result]:
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


def run_migrations() -> None:
    """Run simple SQL migrations at startup (idempotent)."""
    migrations_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "0001_init.sql")
    migrations_path = os.path.abspath(migrations_path)
    if not os.path.exists(migrations_path):
        return
    with open(migrations_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with session() as conn:
        conn.execute(text(sql))
        conn.commit()
