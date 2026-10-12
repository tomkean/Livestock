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
    ("capture", "location", "VARCHAR NOT NULL DEFAULT ''"),
    ("animal", "food", "INTEGER"),
    ("animal", "water", "INTEGER"),
    ("animal", "personal_space", "INTEGER"),
    ("animal", "overall", "INTEGER"),
    ("animal", "seen_at", "DATETIME"),
    ("animal", "wool_per_hour", "FLOAT"),
    ("animal", "wool_per_shear", "INTEGER"),
    ("animal", "wool_regrow_min", "FLOAT"),
    ("animal", "card_name", "VARCHAR NOT NULL DEFAULT ''"),
]


def init_db():
    import models  # noqa: F401  (registers tables)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, ddl in ADDED_COLUMNS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        # Values renamed since: the species is cattle (a cow is the female), not "cow".
        conn.exec_driver_sql("UPDATE animal SET species = 'cattle' WHERE species = 'cow'")
        # The jar icon is low grade fuel; it was filed as "gunpowder" until 12 Oct 2026.
        conn.exec_driver_sql("""UPDATE offer SET items = replace(items, '"gunpowder"', '"low_grade_fuel"')
                                WHERE items LIKE '%"gunpowder"%'""")


def get_session():
    with Session(engine) as session:
        yield session
