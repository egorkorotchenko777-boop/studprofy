import aiosqlite

DB_PATH = "studprofy.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                referrer_id INTEGER DEFAULT NULL,
                bonus_points INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                description TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bonus_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    print("✅ База данных готова")

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c:
            return await c.fetchone()

async def create_user(user_id, username, full_name, referrer_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, referrer_id) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, referrer_id)
        )
        await db.commit()

async def add_bonus(user_id, amount, reason):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET bonus_points = bonus_points + ? WHERE user_id = ?", (amount, user_id))
        await db.execute("INSERT INTO bonus_transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user_id, amount, reason))
        await db.commit()

async def spend_bonus(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT bonus_points FROM users WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            if not row or row[0] < amount:
                return False
        await db.execute("UPDATE users SET bonus_points = bonus_points - ? WHERE user_id = ?", (amount, user_id))
        await db.execute("INSERT INTO bonus_transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user_id, -amount, "Списание"))
        await db.commit()
        return True

async def get_referrals_count(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            return row[0] if row else 0

async def create_order(user_id, description):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO orders (user_id, description) VALUES (?, ?)", (user_id, description))
        await db.execute("UPDATE users SET total_orders = total_orders + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.lastrowid

async def get_all_orders(status="pending"):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT o.*, u.full_name, u.username FROM orders o JOIN users u ON o.user_id = u.user_id WHERE o.status = ?",
            (status,)
        ) as c:
            return await c.fetchall()

async def confirm_order(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)) as c:
            row = await c.fetchone()
            if not row:
                return None
            user_id = row[0]
        await db.execute("UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))
        await db.commit()
        return user_id

async def get_order_user(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT o.*, u.referrer_id FROM orders o JOIN users u ON o.user_id = u.user_id WHERE o.id = ?",
            (order_id,)
        ) as c:
            return await c.fetchone()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY bonus_points DESC") as c:
            return await c.fetchall()
