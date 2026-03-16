import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

# Use sys.modules to mock missing dependencies
import sys
from unittest.mock import MagicMock
sys.modules['pymongo'] = MagicMock()
sys.modules['fastapi'] = MagicMock()
sys.modules['pydantic'] = MagicMock()

# Instead of relying on the actual service logic which requires db setup,
# I'll create a standalone benchmark of the logic.

# Create mock DB
class MockCursor:
    def __init__(self, data):
        self.data = data
    async def to_list(self, length):
        return self.data[:length]

class MockSubscriptions:
    def __init__(self, data):
        self.data = data
        self.updates = []

    def find(self, query):
        return MockCursor(self.data)

    async def find_one(self, query):
        for doc in self.data:
            if doc['_id'] == query['_id']:
                return doc
        return None

    async def update_one(self, query, update):
        self.updates.append((query, update))

    async def update_many(self, query, update):
        # Count matches roughly
        self.updates.append((query, update))
        class Result:
            modified_count = len(self.data)
        return Result()

class MockUsers:
    def __init__(self):
        self.updates = []

    async def update_one(self, query, update):
        self.updates.append((query, update))

    async def update_many(self, query, update):
        self.updates.append((query, update))
        class Result:
            modified_count = 1000 # Mock
        return Result()

class MockDB:
    def __init__(self, subs_data):
        self.subscriptions = MockSubscriptions(subs_data)
        self.users = MockUsers()

# The original slow code
async def stop_subscription(db, sub_id: str) -> bool:
    sub = await db.subscriptions.find_one({"_id": sub_id, "status": "active"})
    if not sub:
        return False
    await db.subscriptions.update_one(
        {"_id": sub_id},
        {"$set": {"status": "stopped"}},
    )
    await db.users.update_one(
        {"_id": sub["user_id"]},
        {"$inc": {"active_subscriptions": -1}},
    )
    return True

async def cleanup_inactive_original(db):
    inactive = await db.subscriptions.find({}).to_list(length=1000)
    for sub in inactive:
        await stop_subscription(db, sub["_id"])
    return len(inactive)

# The optimized code
async def cleanup_inactive_optimized(db):
    inactive = await db.subscriptions.find({}).to_list(length=1000)
    if not inactive:
        return 0

    sub_ids = [sub["_id"] for sub in inactive]
    user_ids = [sub["user_id"] for sub in inactive]

    # 1. Update subscriptions in bulk
    await db.subscriptions.update_many(
        {"_id": {"$in": sub_ids}},
        {"$set": {"status": "stopped"}}
    )

    # 2. Update users in bulk (we decrement by 1 for each subscription stopped)
    # Since multiple subscriptions might belong to the same user, we can group them
    from collections import Counter
    user_counts = Counter(user_ids)

    # Or just loop over the distinct users if that's more efficient, but let's see.
    # Standard mongo doesn't have a single bulk update with different incs easily
    # without bulkWrite, but since we're just decremening:

    # A cleaner way using motor's bulkWrite is ideal, but for now let's just use update_many
    # wait, if a user has multiple inactive subs, update_many with $inc: -1 only applies once!
    # Let's use bulk writes or just a simple loop over unique users (which is still much smaller than N)

    # For this script we just loop over user_counts
    for uid, count in user_counts.items():
        await db.users.update_one(
            {"_id": uid},
            {"$inc": {"active_subscriptions": -count}}
        )

    return len(inactive)

async def main():
    # Generate 1000 inactive subscriptions
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=30)

    data = []
    for i in range(1000):
        data.append({
            "_id": str(uuid.uuid4()),
            "user_id": i % 100, # 100 distinct users
            "status": "active",
            "last_sent": cutoff - timedelta(minutes=1)
        })

    # Test Original
    db_orig = MockDB(data)
    start = time.time()
    await cleanup_inactive_original(db_orig)
    orig_time = time.time() - start

    # Test Optimized
    db_opt = MockDB(data)
    start = time.time()
    await cleanup_inactive_optimized(db_opt)
    opt_time = time.time() - start

    print(f"Original Time: {orig_time:.6f} s")
    print(f"Original Updates (Sub): {len(db_orig.subscriptions.updates)}")
    print(f"Original Updates (User): {len(db_orig.users.updates)}")

    print(f"\nOptimized Time: {opt_time:.6f} s")
    print(f"Optimized Updates (Sub): {len(db_opt.subscriptions.updates)}")
    print(f"Optimized Updates (User): {len(db_opt.users.updates)}")

    print(f"\nSpeedup: {orig_time / opt_time:.2f}x")

if __name__ == "__main__":
    asyncio.run(main())
