import asyncio
import time
from datetime import datetime, timezone

class MockCollection:
    def __init__(self, delay=0.1):
        self.delay = delay

    async def count_documents(self, query):
        await asyncio.sleep(self.delay)
        return 42

class MockDB:
    def __init__(self):
        self.users = MockCollection()
        self.subscriptions = MockCollection()
        self.logs_errors = MockCollection()

async def admin_stats_sequential(db):
    users = await db.users.count_documents({})
    active = await db.subscriptions.count_documents({"status": "active"})
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    errors = await db.logs_errors.count_documents({"timestamp": {"$gte": today}})
    return users, active, errors

async def admin_stats_concurrent(db):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    users, active, errors = await asyncio.gather(
        db.users.count_documents({}),
        db.subscriptions.count_documents({"status": "active"}),
        db.logs_errors.count_documents({"timestamp": {"$gte": today}})
    )
    return users, active, errors

async def main():
    db = MockDB()

    # Measure sequential
    start = time.time()
    await admin_stats_sequential(db)
    seq_time = time.time() - start

    # Measure concurrent
    start = time.time()
    await admin_stats_concurrent(db)
    conc_time = time.time() - start

    print(f"Sequential time: {seq_time:.4f}s")
    print(f"Concurrent time: {conc_time:.4f}s")
    print(f"Improvement: {(seq_time - conc_time) / seq_time * 100:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
