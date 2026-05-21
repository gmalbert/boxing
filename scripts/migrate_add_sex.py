"""One-time migration: add sex column to fighters table."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.db import get_engine
from sqlalchemy import text, inspect

engine = get_engine()
insp = inspect(engine)
cols = [c["name"] for c in insp.get_columns("fighters")]

with engine.connect() as conn:
    if "sex" not in cols:
        conn.execute(text("ALTER TABLE fighters ADD COLUMN sex TEXT DEFAULT 'M'"))
        print("sex column added.")
    conn.execute(text("UPDATE fighters SET sex = 'M' WHERE sex IS NULL"))
    conn.commit()
    result = conn.execute(text("SELECT COUNT(*) FROM fighters WHERE sex IS NULL")).scalar()
    total = conn.execute(text("SELECT COUNT(*) FROM fighters")).scalar()
    print(f"Done. {total} fighters total, {result} with NULL sex remaining.")
