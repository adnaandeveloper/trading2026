import aiosqlite
import os
from datetime import datetime

DB_PATH = "trading.db"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_admin INTEGER DEFAULT 0,
            added_at TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            instrument TEXT,
            size REAL,
            direction TEXT,
            entry REAL,
            tp REAL,
            sl REAL,
            created_at TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            belob REAL,
            dkk REAL,
            note TEXT,
            dato TEXT
        )''')
        await db.execute("INSERT OR IGNORE INTO users (user_id, is_admin, added_at) VALUES (?,?,?)",
                         (ADMIN_ID, 1, datetime.utcnow().isoformat()))
        await db.commit()

async def is_allowed(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None

async def add_user(user_id, username):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO users (user_id, username, is_admin, added_at) VALUES (?,?,0,?)",
                         (user_id, username, datetime.utcnow().isoformat()))
        await db.commit()

async def del_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id=? AND is_admin=0", (user_id,))
        await db.commit()

async def list_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, username FROM users")
        return await cur.fetchall()

async def add_trade(user_id, data):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO trades (user_id,instrument,size,direction,entry,tp,sl,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, data.get('instrument'), data.get('size'), data.get('direction'),
             data.get('entry'), data.get('tp'), data.get('sl'), datetime.utcnow().isoformat())
        )
        await db.commit()

async def add_ledger(user_id, typ, usd, dkk, note):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ledger (user_id,type,belob,dkk,note,dato) VALUES (?,?,?,?,?,?)",
            (user_id, typ, usd, dkk, note, datetime.utcnow().isoformat())
        )
        await db.commit()

async def get_saldo(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT SUM(CASE WHEN type='in' THEN belob ELSE -belob END), "
            "SUM(CASE WHEN type='in' THEN dkk ELSE -dkk END) FROM ledger WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return round(row[0] or 0,2), round(row[1] or 0,0)