import os
import pytest
import asyncio
import aiosqlite
from fastapi.testclient import TestClient
from app.core.config import settings
from app.services.data.db_migrations import run_migrations

TEST_DB_FILE = "test_chatbot.db"


@pytest.fixture(scope="function", autouse=True)
def setup_test_db():
    # Redirect database configuration to the test database file
    settings.database_file = TEST_DB_FILE

    # Setup the test database schema
    async def create_schema():
        async with aiosqlite.connect(TEST_DB_FILE) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await run_migrations(db)

    # Run DB schema creation
    asyncio.run(create_schema())

    yield

    # Teardown the test database file to prevent leakage
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except Exception as e:
            print(f"Error removing test db file: {e}")


@pytest.fixture
def client():
    """Provides a FastAPI test client utilizing the mocked test environment."""
    from app.main import app
    with TestClient(app) as c:
        yield c
