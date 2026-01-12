#!/usr/bin/env python3
"""Quick test to verify DB connection and insert."""
import os
import sys
from dotenv import load_dotenv
import uuid

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

try:
    import psycopg2
except Exception as e:
    print('psycopg2 not available:', e)
    sys.exit(1)

if not DATABASE_URL:
    print('DATABASE_URL not set')
    sys.exit(1)

print(f"DATABASE_URL is set: {DATABASE_URL[:50]}...")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("✓ Connected to database successfully")
    
    # Test insert
    doc_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO documents (id, project_id, filename, file_path, source, status, document_content) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (doc_id, project_id, "test_file.pdf", "https://example.com/test.pdf", "scrape", "pending", None)
    )
    conn.commit()
    print(f"✓ Successfully inserted test document with id={doc_id}")
    
    # Verify it was inserted
    cur.execute("SELECT COUNT(*) FROM documents WHERE id = %s", (doc_id,))
    count = cur.fetchone()[0]
    print(f"✓ Verified: {count} row(s) found with id={doc_id}")
    
    cur.close()
    conn.close()
    print("\n✓ All tests passed!")
    
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {str(e)}")
    sys.exit(1)
