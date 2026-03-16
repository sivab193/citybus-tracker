import pytest
import asyncio
import pytest_asyncio
from citybus.db.mongo import close_db

@pytest_asyncio.fixture(autouse=True)
async def clear_mongo_client():
    """
    Ensure the global MongoDB client is reset after every test.
    This prevents 'Event loop is closed' errors when tests are run in sequence
    with different event loops.
    """
    yield
    await close_db()

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
