import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from app.core.database import engine
from sqlalchemy import text, inspect

inspector = inspect(engine)
columns = [col['name'] for col in inspector.get_columns('bookmarks')]
print("Existing columns in bookmarks:", columns)

if "binder_name" not in columns:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE bookmarks ADD COLUMN binder_name VARCHAR(100) DEFAULT 'General Research';"))
        print("Successfully added 'binder_name' column to 'bookmarks' table.")
else:
    print("'binder_name' column already exists in 'bookmarks' table.")
