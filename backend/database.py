from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


# Columns added after a table was first created: create_all() makes new tables but never alters old ones.
ADDED_COLUMNS = [
    ("animal", "name", "VARCHAR NOT NULL DEFAULT ''"),
    ("animal", "born_at", "DATETIME"),
    ("animal", "pen", "VARCHAR NOT NULL DEFAULT ''"),
    ("animal", "food", "INTEGER"),
    ("animal", "water", "INTEGER"),
    ("animal", "personal_space", "INTEGER"),
    ("animal", "overall", "INTEGER"),
    ("animal", "seen_at", "DATETIME"),
]


def init_db():
    import models  # noqa: F401  (registers tables)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, ddl in ADDED_COLUMNS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def get_session():
    with Session(engine) as session:
        yield session
