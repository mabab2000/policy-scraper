#!/usr/bin/env python3
"""Migration to alter project_id from UUID to TEXT"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

try:
    import psycopg2
except Exception as e:
    print('psycopg2 is not installed:', e)
    sys.exit(2)

if not DATABASE_URL:
    print('DATABASE_URL is not set. Aborting.')
    sys.exit(1)

ALTER_COLUMN_SQL = """
ALTER TABLE documents ALTER COLUMN project_id TYPE TEXT USING project_id::TEXT;
"""


def main():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        print('Connected to database, altering project_id column to TEXT...')
        cur.execute(ALTER_COLUMN_SQL)
        conn.commit()
        cur.close()
        conn.close()
        print('Migration completed: project_id column is now TEXT.')
    except Exception as e:
        print('Migration failed:', str(e))
        try:
            conn.close()
        except Exception:
            pass
        sys.exit(3)


if __name__ == '__main__':
    main()
