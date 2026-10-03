"""启动配置：定位 core/、把 secrets.toml 注入环境变量。

core/ 只有一份，放在仓库根目录（api/ 的上一级）。本项目通过 sys.path 复用它，
而不是拷贝——拷贝一份出来迟早会和网页版分叉。路径可用 EDU_CORE_PATH 覆盖。
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
API_ROOT = APP_DIR.parent
# 仓库根 = api/ 的上一级，core/ 与 .streamlit/ 都在那里
DEFAULT_CORE_PATH = API_ROOT.parent


def core_path() -> Path:
    return Path(os.environ.get("EDU_CORE_PATH") or DEFAULT_CORE_PATH).resolve()


def ensure_core_importable() -> Path:
    """把 core/ 所在仓库根目录加进 sys.path，之后 `import core` 即可用。"""
    root = core_path()
    if not (root / "core").is_dir():
        raise RuntimeError(
            f"找不到 core/：{root}\n"
            f"请设置 EDU_CORE_PATH 指向仓库根目录（含 core/ 的那一级）。"
        )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


# --------------------------------------------------------------------------- #
# secrets.toml → 环境变量
# --------------------------------------------------------------------------- #
# 与 scripts/extract_textbooks.py 的做法一致：不复制配置，读同一份文件。
# core.runtime.secret() 是「环境变量优先、st.secrets 回落」，注进来即可两边一致。
_SECRET_KEYS = (
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_SEED_DEMO",
    "AUTH_OTP_SECRET", "AUTH_DEV_MODE",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USE_SSL", "SMTP_LOGIN", "SMTP_PASSWORD", "SMTP_SENDER_EMAIL",
    "LLM_BASE_URL", "LLM_MODEL", "LLM_VISION_MODEL",
    "API_JWT_SECRET", "API_TOKEN_TTL_HOURS",
)

_secrets_loaded = False


def load_secrets_into_env() -> Path | None:
    """把网页版的 .streamlit/secrets.toml 注入 os.environ（已存在的环境变量优先）。"""
    global _secrets_loaded
    if _secrets_loaded:
        return None
    _secrets_loaded = True

    path = core_path() / ".streamlit" / "secrets.toml"
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    for name in _SECRET_KEYS:
        value = data.get(name)
        if value not in (None, "") and not os.environ.get(name):
            os.environ[name] = str(value)

    # 大模型 key 池：core.llm 认 JSON 数组形式的环境变量
    keys = data.get("LLM_API_KEYS")
    if keys and not os.environ.get("LLM_API_KEYS"):
        os.environ["LLM_API_KEYS"] = json.dumps([str(k) for k in keys], ensure_ascii=False)
    elif data.get("LLM_API_KEY") and not os.environ.get("LLM_API_KEY"):
        os.environ["LLM_API_KEY"] = str(data["LLM_API_KEY"])

    return path


def bootstrap() -> None:
    """在任何 core 导入之前调用：定位 core/ + 注入配置。"""
    ensure_core_importable()
    load_secrets_into_env()

    # JWT 密钥：没单独配就复用 AUTH_OTP_SECRET，保证开箱可用。
    # 生产环境建议显式设置 API_JWT_SECRET——轮换 OTP 密钥时不会把所有人踢下线。
    if not os.environ.get("API_JWT_SECRET"):
        os.environ["API_JWT_SECRET"] = os.environ.get("AUTH_OTP_SECRET") or ""


# --------------------------------------------------------------------------- #
# 运行参数
# --------------------------------------------------------------------------- #
def jwt_secret() -> str:
    return os.environ.get("API_JWT_SECRET") or os.environ.get("AUTH_OTP_SECRET") or ""


def token_ttl_hours() -> int:
    try:
        return max(1, int(os.environ.get("API_TOKEN_TTL_HOURS") or 168))  # 默认 7 天
    except ValueError:
        return 168


def cors_origins() -> list[str]:
    """允许的跨域来源。

    小程序端不走 CORS（微信请求不带 Origin 校验），这里主要是给 H5 调试用。
    默认放开 localhost 便于本地联调；生产用 API_CORS_ORIGINS 显式收敛。
    """
    raw = os.environ.get("API_CORS_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return ["http://localhost:5173", "http://localhost:8080", "http://127.0.0.1:5173"]
