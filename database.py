"""SQLite persistence and authentication helpers for KeBan AI."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path


DB_PATH = Path(os.environ.get("EDU_DB_PATH", "data/edu_platform.db"))


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, expected = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def init_db():
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student',
                vip_until REAL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS otp_codes (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                code_hash TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                plan TEXT NOT NULL,
                price INTEGER NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                reply TEXT,
                replied_at REAL
            );
            CREATE TABLE IF NOT EXISTS learning_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                kind TEXT NOT NULL,
                score INTEGER NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            now = time.time()
            db.executemany(
                "INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                [
                    ("admin", "admin@keban.ai", hash_password("123456"), "admin", now),
                    ("student", "student@example.com", hash_password("123456"), "student", now),
                ],
            )


def get_user_by_username(username):
    with _connect() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return dict(row) if row else None


def get_user(user_id):
    with _connect() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def authenticate(username, password):
    user = get_user_by_username(username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def issue_otp(email, code_hash):
    now = time.time()
    with _connect() as db:
        previous = db.execute(
            "SELECT created_at FROM otp_codes WHERE email = ?", (email.strip(),)
        ).fetchone()
        if previous and now - previous["created_at"] < 60:
            return False
        db.execute(
            "INSERT INTO otp_codes(email,code_hash,expires_at,created_at,attempts) VALUES(?,?,?,?,0) "
            "ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash, expires_at=excluded.expires_at, "
            "created_at=excluded.created_at, attempts=0",
            (email.strip(), code_hash, now + 600, now),
        )
    return True


def verify_otp(email, code_hash):
    now = time.time()
    with _connect() as db:
        row = db.execute("SELECT * FROM otp_codes WHERE email = ?", (email.strip(),)).fetchone()
        if not row or row["expires_at"] < now or row["attempts"] >= 5:
            return False
        if hmac.compare_digest(row["code_hash"], code_hash):
            db.execute("DELETE FROM otp_codes WHERE email = ?", (email.strip(),))
            return True
        db.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE email = ?", (email.strip(),))
        return False


def create_user(username, email, password):
    with _connect() as db:
        db.execute(
            "INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            (username.strip(), email.strip().lower(), hash_password(password), "student", time.time()),
        )
        row = db.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return dict(row)


def record_learning(user_id, kind, score):
    with _connect() as db:
        db.execute(
            "INSERT INTO learning_events(user_id,kind,score,created_at) VALUES(?,?,?,?)",
            (user_id, kind, score, time.time()),
        )


def get_learning(user_id, limit=8):
    with _connect() as db:
        rows = db.execute(
            "SELECT kind,score,created_at FROM learning_events WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def add_message(user_id, content):
    with _connect() as db:
        db.execute(
            "INSERT INTO messages(user_id,content,created_at) VALUES(?,?,?)",
            (user_id, content.strip(), time.time()),
        )


def buy_membership(user_id, plan, price, days):
    now = time.time()
    with _connect() as db:
        user = db.execute("SELECT vip_until FROM users WHERE id=?", (user_id,)).fetchone()
        start = max(now, user["vip_until"] or now)
        expiry = start + days * 86400
        db.execute("UPDATE users SET vip_until=? WHERE id=?", (expiry, user_id))
        db.execute(
            "INSERT INTO orders(user_id,plan,price,created_at) VALUES(?,?,?,?)",
            (user_id, plan, price, now),
        )
    return expiry


def get_admin_data():
    with _connect() as db:
        users = db.execute(
            "SELECT username,email,role,vip_until,created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        orders = db.execute(
            "SELECT u.username,o.plan,o.price,o.created_at FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.created_at DESC"
        ).fetchall()
        messages = db.execute(
            "SELECT m.id,u.username,m.content,m.created_at,m.reply,m.replied_at FROM messages m JOIN users u ON u.id=m.user_id ORDER BY m.created_at DESC"
        ).fetchall()
        stats = db.execute(
            "SELECT COUNT(*) AS users, (SELECT COUNT(*) FROM orders) AS orders, COALESCE((SELECT SUM(price) FROM orders),0) AS revenue FROM users"
        ).fetchone()
        return [dict(r) for r in users], [dict(r) for r in orders], [dict(r) for r in messages], dict(stats)


def reply_message(message_id, reply):
    with _connect() as db:
        db.execute(
            "UPDATE messages SET reply=?,replied_at=? WHERE id=?",
            (reply.strip(), time.time(), message_id),
        )
