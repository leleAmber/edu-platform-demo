"""数据访问层：MySQL 持久化存储。

职责：
1. 管理数据库连接池（进程内单例），供全部页面与模块复用；
2. 首次连接时自动建表（CREATE TABLE IF NOT EXISTS）并写入初始账号；
3. 提供全部业务 CRUD，页面只允许调用这些方法，不直接写 SQL。

设计要点：
- 连接信息从环境变量或 st.secrets 读取，不硬编码，本地开发与线上部署同一套代码；
- 用整型自增主键保证并发写入唯一，展示用的 U001 / O001 / M001 由主键派生；
- 所有 datetime 统一转成 "%Y-%m-%d %H:%M:%S" 字符串返回，与页面展示逻辑保持一致；
- 密码使用 PBKDF2-SHA256 加盐哈希存储，绝不落明文。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 内置初始账号（仅在 users 表为空时写入）。商用部署请改密或关闭种子开关。
DEMO_ACCOUNTS = (
    {"username": "student", "email": "student@keban.ai", "password": "123456", "role": "student"},
    {"username": "admin", "email": "admin@keban.ai", "password": "123456", "role": "admin"},
)

_PBKDF2_ITERATIONS = 120_000

_ENGINE = None
_ENGINE_LOCK = threading.Lock()
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()

# 允许通过 update_user 修改的列，防止外部传入任意列名
_UPDATABLE_USER_COLUMNS = frozenset({"username", "email", "password", "role", "vip_until", "vip_plan"})


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def _setting(name: str, default: str = "") -> str:
    """读取配置：环境变量优先，其次 st.secrets，最后取默认值。

    线上部署通常用环境变量注入；Streamlit Cloud 之类平台则用 secrets。
    """
    value = os.environ.get(name)
    if value:
        return value
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def get_db_config() -> dict:
    """组装数据库连接配置。缺少用户名时抛出异常，避免连到错误的库。"""
    user = _setting("DB_USER")
    if not user:
        raise RuntimeError(
            "未配置数据库连接：请在 .streamlit/secrets.toml 或环境变量中设置 "
            "DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME"
        )
    return {
        "host": _setting("DB_HOST", "127.0.0.1"),
        "port": int(_setting("DB_PORT", "3306") or 3306),
        "user": user,
        "password": _setting("DB_PASSWORD"),
        "name": _setting("DB_NAME", "keban_ai"),
    }


def _get_engine():
    """获取进程内唯一的数据库引擎（含连接池）。

    模块级单例即可跨 Streamlit 的多次脚本重跑复用：脚本每次都重新执行，
    但已导入的模块常驻 sys.modules，因此连接池不会被反复创建。
    """
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                config = get_db_config()
                # 用 URL.create 组装，密码里的 @ : / 等字符会被正确转义
                url = URL.create(
                    "mysql+pymysql",
                    username=config["user"],
                    password=config["password"],
                    host=config["host"],
                    port=config["port"],
                    database=config["name"],
                    query={"charset": "utf8mb4"},
                )
                _ENGINE = create_engine(
                    url,
                    pool_size=5,        # 常驻连接数
                    max_overflow=10,    # 高峰期可临时超出的连接数
                    pool_recycle=3600,  # 一小时回收一次，避免被 MySQL 的 wait_timeout 断开
                    pool_pre_ping=True,  # 取用前先探活，自动剔除失效连接
                    future=True,
                )
    return _ENGINE


@contextmanager
def _raw_connect():
    """开启一个自动提交的事务；出异常自动回滚。"""
    with _get_engine().begin() as conn:
        yield conn


@contextmanager
def _connect():
    """业务用连接：保证表结构已就绪。"""
    _ensure_schema()
    with _raw_connect() as conn:
        yield conn


def health_check() -> tuple[bool, str]:
    """探测数据库可用性，供页面或运维脚本调用。"""
    try:
        with _raw_connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
        config = get_db_config()
        return True, f"已连接 {config['host']}:{config['port']}/{config['name']}（MySQL {version}）"
    except Exception as exc:  # noqa: BLE001 - 诊断用途，需要拿到任何异常
        return False, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def now_text() -> str:
    """统一的本地时间字符串（秒级）。"""
    return datetime.now().strftime(DATE_FORMAT)


def _to_datetime(value) -> datetime | None:
    """把字符串/None 统一转成 datetime，供写入 DATETIME 列使用。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    for fmt in (DATE_FORMAT, "%Y-%m-%d"):
        try:
            return datetime.strptime(text_value, fmt)
        except ValueError:
            continue
    return None


def _to_text(value) -> str | None:
    """把 datetime/None 统一转成展示用字符串。"""
    if isinstance(value, datetime):
        return value.strftime(DATE_FORMAT)
    if value is None:
        return None
    return str(value)


def hash_password(password: str) -> str:
    """把明文密码转换为 pbkdf2_sha256$迭代次数$盐$摘要。"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码；使用 hmac 常量时间比较，避免时序侧信道。"""
    if not stored:
        return False
    if not str(stored).startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(str(stored), str(password))
    try:
        _, iterations, salt, digest = str(stored).split("$")
        calculated = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculated.hex(), digest)


# --------------------------------------------------------------------------- #
# 建表与初始数据
# --------------------------------------------------------------------------- #
# 与 schema.sql 等价；用 CREATE TABLE IF NOT EXISTS 保证可重复执行
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
      id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      username   VARCHAR(50)     NOT NULL,
      email      VARCHAR(120)    NOT NULL,
      password   VARCHAR(255)    NOT NULL,
      role       VARCHAR(20)     NOT NULL DEFAULT 'student',
      vip_until  DATETIME        NULL,
      vip_plan   VARCHAR(20)     NULL,
      created_at DATETIME        NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_users_username (username),
      UNIQUE KEY uk_users_email (email),
      KEY idx_users_role (role),
      KEY idx_users_vip_until (vip_until)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
      id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      username   VARCHAR(50)     NOT NULL,
      plan_name  VARCHAR(20)     NOT NULL,
      amount     DECIMAL(10,2)   NOT NULL DEFAULT 0.00,
      days       INT UNSIGNED    NOT NULL DEFAULT 0,
      vip_until  DATETIME        NULL,
      status     VARCHAR(20)     NOT NULL DEFAULT '已支付',
      pay_method VARCHAR(20)     NOT NULL DEFAULT '模拟支付',
      created_at DATETIME        NOT NULL,
      PRIMARY KEY (id),
      KEY idx_orders_username (username),
      KEY idx_orders_created_at (created_at),
      KEY idx_orders_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
      id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      username   VARCHAR(50)     NOT NULL,
      content    TEXT            NOT NULL,
      is_replied TINYINT(1)      NOT NULL DEFAULT 0,
      reply      TEXT            NULL,
      created_at DATETIME        NOT NULL,
      replied_at DATETIME        NULL,
      PRIMARY KEY (id),
      KEY idx_messages_created_at (created_at),
      KEY idx_messages_is_replied (is_replied),
      KEY idx_messages_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_records (
      id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      username   VARCHAR(50)     NOT NULL,
      module     VARCHAR(50)     NOT NULL,
      unit       VARCHAR(100)    NULL,
      score      INT             NULL,
      level      VARCHAR(20)     NULL,
      created_at DATETIME        NOT NULL,
      PRIMARY KEY (id),
      KEY idx_records_user_time (username, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


def init_schema() -> None:
    """建表并写入初始账号（幂等，可重复调用）。"""
    global _SCHEMA_READY
    with _raw_connect() as conn:
        for statement in _SCHEMA_STATEMENTS:
            conn.execute(text(statement))
        _seed_accounts(conn)
    _SCHEMA_READY = True


def _ensure_schema() -> None:
    """保证表结构就绪；全局只真正执行一次。"""
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if not _SCHEMA_READY:
            init_schema()


def _seed_accounts(conn) -> None:
    """users 表为空时写入初始账号。设 DB_SEED_DEMO=0 可关闭。"""
    if _setting("DB_SEED_DEMO", "1") == "0":
        return
    count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    if count:
        return
    for account in DEMO_ACCOUNTS:
        conn.execute(
            text(
                "INSERT INTO users (username, email, password, role, vip_until, vip_plan, created_at) "
                "VALUES (:username, :email, :password, :role, NULL, NULL, :created_at)"
            ),
            {
                "username": account["username"],
                "email": account["email"],
                "password": hash_password(account["password"]),
                "role": account["role"],
                "created_at": datetime.now(),
            },
        )


# --------------------------------------------------------------------------- #
# 行转换
# --------------------------------------------------------------------------- #
def _user_row(row) -> dict:
    """把用户行转成与旧版 JSON 结构一致的字典，页面无需改动。"""
    data = dict(row)
    return {
        "user_id": f"U{data['id']:03d}",
        "username": data["username"],
        "email": data["email"],
        "password": data["password"],
        "role": data["role"],
        "vip_until": _to_text(data["vip_until"]),
        "vip_plan": data["vip_plan"],
        "created_at": _to_text(data["created_at"]),
    }


def _order_row(row) -> dict:
    data = dict(row)
    return {
        "order_id": f"O{data['id']:03d}",
        "username": data["username"],
        "plan_name": data["plan_name"],
        "amount": float(data["amount"]),
        "days": int(data["days"]),
        "vip_until": _to_text(data["vip_until"]),
        "status": data["status"],
        "pay_method": data["pay_method"],
        "created_at": _to_text(data["created_at"]),
    }


def _message_row(row) -> dict:
    data = dict(row)
    return {
        "msg_id": f"M{data['id']:03d}",
        "username": data["username"],
        "content": data["content"],
        "is_replied": bool(data["is_replied"]),
        "reply": data["reply"] or "",
        "created_at": _to_text(data["created_at"]),
        "replied_at": _to_text(data["replied_at"]) or "",
    }


def _record_row(row) -> dict:
    data = dict(row)
    return {
        "time": _to_text(data["created_at"]),
        "module": data["module"],
        "unit": data["unit"] or "",
        "score": data["score"],
        "level": data["level"] or "",
    }


# --------------------------------------------------------------------------- #
# 用户
# --------------------------------------------------------------------------- #
def get_all_users() -> list[dict]:
    """获取全部用户（按注册时间倒序）。"""
    with _connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM users ORDER BY created_at DESC, id DESC")
        ).mappings().all()
    return [_user_row(row) for row in rows]


def get_user_by_username(username: str) -> dict | None:
    """按用户名查询；utf8mb4_unicode_ci 排序规则下大小写不敏感。"""
    target = (username or "").strip()
    if not target:
        return None
    with _connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE username = :username LIMIT 1"),
            {"username": target},
        ).mappings().first()
    return _user_row(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    """按邮箱查询，大小写不敏感。"""
    target = (email or "").strip()
    if not target:
        return None
    with _connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE email = :email LIMIT 1"),
            {"email": target},
        ).mappings().first()
    return _user_row(row) if row else None


def add_new_user(user_info: dict) -> dict | None:
    """新增注册用户；用户名或邮箱已存在时返回 None。

    唯一性最终由数据库唯一索引保证，即使并发注册也不会写入重复数据。
    """
    username = str(user_info.get("username", "")).strip()
    if not username:
        return None
    try:
        with _connect() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users (username, email, password, role, vip_until, vip_plan, created_at) "
                    "VALUES (:username, :email, :password, :role, :vip_until, :vip_plan, :created_at)"
                ),
                {
                    "username": username,
                    "email": str(user_info.get("email", "")).strip(),
                    "password": user_info.get("password", ""),
                    "role": user_info.get("role", "student"),
                    "vip_until": _to_datetime(user_info.get("vip_until")),
                    "vip_plan": user_info.get("vip_plan"),
                    "created_at": datetime.now(),
                },
            )
            new_id = result.lastrowid
    except IntegrityError:
        return None
    return get_user_by_id(new_id)


def get_user_by_id(user_id: int) -> dict | None:
    """按内部主键查询用户。"""
    with _connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE id = :id LIMIT 1"), {"id": user_id}
        ).mappings().first()
    return _user_row(row) if row else None


def update_user(username: str, update_dict: dict) -> dict | None:
    """更新用户信息（如开通会员写入 vip_until），返回更新后的用户。"""
    target = (username or "").strip()
    if not target:
        return None

    fields = {key: value for key, value in update_dict.items() if key in _UPDATABLE_USER_COLUMNS}
    if not fields:
        return get_user_by_username(target)

    assignments = []
    params: dict = {"username": target}
    for column, value in fields.items():
        assignments.append(f"{column} = :{column}")
        params[column] = _to_datetime(value) if column == "vip_until" else value

    with _connect() as conn:
        result = conn.execute(
            text(f"UPDATE users SET {', '.join(assignments)} WHERE username = :username"),
            params,
        )
        if result.rowcount == 0:
            return None
    return get_user_by_username(target)


# --------------------------------------------------------------------------- #
# 订单
# --------------------------------------------------------------------------- #
def get_all_orders() -> list[dict]:
    """获取全部会员订单（按下单时间倒序）。"""
    with _connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM orders ORDER BY created_at DESC, id DESC")
        ).mappings().all()
    return [_order_row(row) for row in rows]


def add_order(order_info: dict) -> dict:
    """新增一条会员订单记录，返回写入后的订单。"""
    username = str(order_info.get("username", "")).strip()
    with _connect() as conn:
        result = conn.execute(
            text(
                "INSERT INTO orders "
                "(username, plan_name, amount, days, vip_until, status, pay_method, created_at) "
                "VALUES (:username, :plan_name, :amount, :days, :vip_until, :status, :pay_method, :created_at)"
            ),
            {
                "username": username,
                "plan_name": str(order_info.get("plan_name", "")),
                "amount": order_info.get("amount", 0),
                "days": int(order_info.get("days", 0) or 0),
                "vip_until": _to_datetime(order_info.get("vip_until")),
                "status": order_info.get("status", "已支付"),
                "pay_method": order_info.get("pay_method", "模拟支付"),
                "created_at": datetime.now(),
            },
        )
        new_id = result.lastrowid
        row = conn.execute(
            text("SELECT * FROM orders WHERE id = :id"), {"id": new_id}
        ).mappings().first()
    return _order_row(row)


# --------------------------------------------------------------------------- #
# 客服留言
# --------------------------------------------------------------------------- #
def get_all_messages() -> list[dict]:
    """获取全部客服留言（按提交时间倒序）。"""
    with _connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM messages ORDER BY created_at DESC, id DESC")
        ).mappings().all()
    return [_message_row(row) for row in rows]


def add_message(msg_info: dict) -> dict:
    """新增客服留言，返回写入后的留言。"""
    with _connect() as conn:
        result = conn.execute(
            text(
                "INSERT INTO messages (username, content, is_replied, reply, created_at, replied_at) "
                "VALUES (:username, :content, 0, NULL, :created_at, NULL)"
            ),
            {
                "username": str(msg_info.get("username", "")).strip(),
                "content": str(msg_info.get("content", "")),
                "created_at": datetime.now(),
            },
        )
        new_id = result.lastrowid
        row = conn.execute(
            text("SELECT * FROM messages WHERE id = :id"), {"id": new_id}
        ).mappings().first()
    return _message_row(row)


def update_message(msg_id, reply_content: str) -> dict | None:
    """管理员回复留言，并标记 is_replied = 1。

    msg_id 形如 "M001"，这里解析出数字主键；也直接接受纯数字。
    """
    raw = str(msg_id or "").strip().lstrip("Mm")
    if not raw.isdigit():
        return None

    with _connect() as conn:
        result = conn.execute(
            text(
                "UPDATE messages SET reply = :reply, is_replied = 1, replied_at = :replied_at "
                "WHERE id = :id"
            ),
            {
                "reply": (reply_content or "").strip(),
                "replied_at": datetime.now(),
                "id": int(raw),
            },
        )
        if result.rowcount == 0:
            return None
        row = conn.execute(
            text("SELECT * FROM messages WHERE id = :id"), {"id": int(raw)}
        ).mappings().first()
    return _message_row(row)


# --------------------------------------------------------------------------- #
# 学习记录（持久化到数据库，学情分析依赖跨会话的历史数据）
# --------------------------------------------------------------------------- #
def add_learning_record(username: str, record: dict) -> None:
    """记录一次学习行为，用于首页「最近学习记录」与学情诊断。"""
    with _connect() as conn:
        conn.execute(
            text(
                "INSERT INTO learning_records (username, module, unit, score, level, created_at) "
                "VALUES (:username, :module, :unit, :score, :level, :created_at)"
            ),
            {
                "username": str(username or "").strip(),
                "module": str(record.get("module", "")),
                "unit": str(record.get("unit", "") or ""),
                "score": int(record["score"]) if record.get("score") is not None else None,
                "level": str(record.get("level", "") or ""),
                "created_at": _to_datetime(record.get("time")) or datetime.now(),
            },
        )


def get_learning_records(username: str, limit: int = 50) -> list[dict]:
    """读取该用户的学习记录，最新的排在最前。"""
    target = str(username or "").strip()
    if not target:
        return []
    with _connect() as conn:
        rows = conn.execute(
            text(
                "SELECT * FROM learning_records WHERE username = :username "
                "ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            {"username": target, "limit": int(limit)},
        ).mappings().all()
    return [_record_row(row) for row in rows]
