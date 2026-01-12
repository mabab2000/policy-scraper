#!/usr/bin/env python3
"""Migration script to create the `documents` table if it does not exist.
Reads `DATABASE_URL` from environment or .env and attempts to connect using psycopg2.

Usage:
    python migrations/create_documents_table.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

try:
    import psycopg2
    from psycopg2 import sql
except Exception as e:
    print('psycopg2 is not installed or cannot be imported:', e)
    sys.exit(2)

if not DATABASE_URL:
    print('DATABASE_URL is not set in environment (.env). Aborting.')
    sys.exit(1)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    project_id TEXT,
    filename TEXT,
    file_path TEXT,
    source TEXT,
    status TEXT DEFAULT 'pending',
    document_content TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents (project_id);
"""


def main():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print('Connected to database, creating table if not exists...')
        cur.execute(CREATE_TABLE_SQL)
        cur.execute(CREATE_INDEX_SQL)
        conn.commit()
        cur.close()
        conn.close()
        print('Migration completed: `documents` table is present (or already existed).')
    except Exception as e:
        print('Migration failed:', str(e))
        try:
            conn.close()
        except Exception:
            pass
        sys.exit(3)


if __name__ == '__main__':
    main()
