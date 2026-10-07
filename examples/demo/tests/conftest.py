import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine.url import make_url

DEMO_ROOT = Path(__file__).resolve().parents[1]
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))


def demo_db_parts():
    url = os.environ.get("DEMO_TEST_DATABASE_URL", "").strip()
    if url:
        parsed = make_url(url)
        if not parsed.host or not parsed.database:
            return None
        return {
            "host": parsed.host,
            "port": int(parsed.port or 5432),
            "user": parsed.username or "postgres",
            "password": parsed.password or "",
            "database": parsed.database,
        }
    host = os.environ.get("DEMO_TEST_DB_HOST", "").strip()
    name = os.environ.get("DEMO_TEST_DB_NAME", "").strip()
    if not host or not name:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("DEMO_TEST_DB_PORT") or 5432),
        "user": os.environ.get("DEMO_TEST_DB_USER") or "postgres",
        "password": os.environ.get("DEMO_TEST_DB_PASSWORD") or "",
        "database": name,
    }


@pytest.fixture
def db_parts():
    parts = demo_db_parts()
    if parts is None:
        pytest.skip("DEMO_TEST_DATABASE_URL is not set")
    return parts
