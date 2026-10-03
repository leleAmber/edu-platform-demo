"""端到端接口测试：先起服务，再跑本脚本。

    cd api
    python run.py                        # 另开一个终端
    python -m tests.test_api             # 本脚本

刻意用真实 HTTP（requests 打真服务）而不是 FastAPI TestClient：
TestClient 会绕过 uvicorn 的线程池调度，而本项目最关键的一条假设恰恰是
「同步接口跑在线程池里，仍能读到中间件绑定的当前用户」——只有打真服务才测得出来。

覆盖：鉴权 401/403、越权访问他人 job、题目脱敏、异步任务链路、内容级门禁。
会临时建一个免费测试账号，跑完删掉。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402,F401  —— 触发 bootstrap，把 core/ 加进 sys.path

from sqlalchemy import text  # noqa: E402

from core import database  # noqa: E402

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

FREE_USER = "apitest_free"
FREE_PASS = "test123456"
BOOK = "必修一"

passed = 0
failed = 0


# --------------------------------------------------------------------------- #
# HTTP 小工具
# --------------------------------------------------------------------------- #
def auth(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def get(path: str, token: str | None = None, **kw) -> requests.Response:
    return requests.get(f"{BASE_URL}{path}", headers=auth(token), timeout=60, **kw)


def post(path: str, token: str | None = None, **kw) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", headers=auth(token), timeout=180, **kw)


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  OK   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}  {detail[:200]}")


def login(username: str, password: str) -> str:
    resp = post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# --------------------------------------------------------------------------- #
# 测试账号
# --------------------------------------------------------------------------- #
def ensure_free_user() -> None:
    with database._raw_connect() as conn:
        conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": FREE_USER})
    database.add_new_user({
        "username": FREE_USER,
        "email": f"{FREE_USER}@test.local",
        "password": database.hash_password(FREE_PASS),
        "role": "student",
        "vip_until": None,
    })


def drop_free_user() -> None:
    with database._raw_connect() as conn:
        conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": FREE_USER})


def wait_job(token: str, job_id: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = get(f"/jobs/{job_id}", token)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] != "pending":
            return body
        time.sleep(1.5)
    raise TimeoutError(f"任务 {job_id} 超时未完成")


# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        r = get("/health")
        if r.status_code not in (200, 503):
            print(f"服务没起来？{BASE_URL} -> {r.status_code}\n先运行：python run.py")
            return 2
    except requests.ConnectionError:
        print(f"连不上 {BASE_URL}\n先运行：python run.py")
        return 2

    ensure_free_user()

    try:
        print("\n=== 健康检查 / 鉴权 ===")
        r = get("/health")
        check("/health 返回 200", r.status_code == 200, r.text)
        check("数据库连通", r.json().get("ok") is True, r.text)

        r = get("/auth/me")
        check("无 token 访问 /auth/me -> 401", r.status_code == 401, r.text)

        r = get("/auth/me", "garbage.token.here")
        check("伪造 token -> 401", r.status_code == 401, r.text)

        r = post("/auth/login", json={"username": "student", "password": "wrong"})
        check("错误密码 -> 401", r.status_code == 401, r.text)

        vip_token = login("student", "123456")
        free_token = login(FREE_USER, FREE_PASS)
        admin_token = login("admin", "123456")
        check("登录成功拿到 token", bool(vip_token))

        r = get("/auth/me", vip_token)
        check("GET /auth/me 返回用户",
              r.status_code == 200 and r.json()["user"]["username"] == "student", r.text)
        check("响应不含密码哈希", "password" not in r.json()["user"], r.text)
        check("VIP 账号 is_vip=true", r.json()["user"]["is_vip"] is True, r.text)
        check("用户上下文在线程池里可读（/auth/me 走同步依赖）", r.status_code == 200, r.text)

        r = get("/auth/me", free_token)
        check("免费账号 is_vip=false", r.json()["user"]["is_vip"] is False, r.text)

        print("\n=== 教材 / 单元 ===")
        r = get("/textbooks", vip_token)
        books = r.json()["books"]
        check("教材目录非空", r.status_code == 200 and len(books) > 0, r.text)

        r = get(f"/textbooks/{BOOK}/units", vip_token)
        units = r.json()["units"]
        check("单元列表非空", len(units) > 0, r.text)

        r = get("/textbooks/不存在的书/units", vip_token)
        check("不存在的教材 -> 404", r.status_code == 404, r.text)

        unit = units[0]
        r = get(f"/textbooks/{BOOK}/units/{unit}", vip_token)
        content = r.json()
        check("单元内容含单词", len(content.get("words", [])) > 0,
              f"words={len(content.get('words', []))}")

        quiz = content.get("preview_quiz", [])
        check("预习练习非空", len(quiz) > 0, f"count={len(quiz)}")
        leaked = [q for q in quiz if "answer" in q or "explain" in q]
        check("下载的练习不含答案", not leaked, f"泄漏 {len(leaked)} 题")

        print("\n=== 预习练习批改 ===")
        answers = {str(i): q["options"][0] for i, q in enumerate(quiz)}
        r = post("/quiz/grade", vip_token, json={
            "book": BOOK, "unit": unit, "quiz_type": "preview", "answers": answers,
        })
        graded = r.json()
        check("批改返回得分", r.status_code == 200 and "score" in graded, r.text)
        check("批改返回掌握度", "mastery" in graded and "level" in graded, r.text)
        check("批改结果含逐题解析", len(graded.get("details", [])) == len(quiz), r.text)

        print("\n=== 模拟试卷（VIP） ===")
        r = get("/mock-exam", free_token, params={"book": BOOK})
        check("免费账号访问模拟卷 -> 403", r.status_code == 403, r.text)

        r = get("/mock-exam", vip_token, params={"book": BOOK})
        exam = r.json()
        check("VIP 拿到试卷", r.status_code == 200 and "sections" in exam, r.text)

        exam_questions = []
        for sec in exam["sections"]:
            exam_questions.extend(sec.get("questions", []))
            for p in sec.get("passages", []):
                exam_questions.extend(p.get("questions", []))
        check("试卷有客观题", len(exam_questions) > 0, f"count={len(exam_questions)}")
        leaked = [q for q in exam_questions if "answer" in q or "explain" in q]
        check("试卷不含答案", not leaked, f"泄漏 {len(leaked)} 题")

        print("\n=== 交卷（异步任务） ===")
        r = post("/mock-exam/grade", vip_token,
                 json={"book": BOOK, "answers": {q["id"]: "A" for q in exam_questions}, "writings": {}})
        check("交卷返回 job_id", r.status_code == 200 and "job_id" in r.json(), r.text)
        exam_job = r.json()["job_id"]

        r = get(f"/jobs/{exam_job}", free_token)
        check("他人 job -> 404（不泄漏存在性）", r.status_code == 404, r.text)

        job = wait_job(vip_token, exam_job)
        check("交卷任务完成", job["status"] == "done",
              f"status={job['status']} err={job.get('error')}")
        check("交卷结果含总分", isinstance((job.get("result") or {}).get("total"), int),
              str(job.get("result"))[:120])

        print("\n=== 学情诊断（VIP） ===")
        r = get("/diagnosis", free_token)
        check("免费账号访问诊断 -> 403", r.status_code == 403, r.text)

        r = get("/diagnosis", vip_token)
        diag = r.json()
        check("VIP 拿到诊断", r.status_code == 200 and "radar" in diag, r.text)
        check("雷达图 4 个维度", len(diag["radar"]["values"]) == 4, str(diag.get("radar")))
        check("诊断含改进建议", len(diag["suggestions"]) > 0, r.text)

        r2 = get("/diagnosis", vip_token)
        check("同一批记录诊断结果稳定", r2.json()["radar"]["values"] == diag["radar"]["values"], "")

        print("\n=== 学习记录 ===")
        r = get("/records", vip_token)
        check("学习记录可读", r.status_code == 200 and r.json()["count"] > 0, r.text)

        print("\n=== 作业批改（免费用户：内容级门禁） ===")
        # 必须在开通会员之前跑：下面「会员」一段会把 free_token 升级成 VIP，
        # 之后再测免费权限就测不到了
        r = post("/homework/grade", free_token, json={
            "text": "I go to school yesterday and meet my friend. He is very happy.",
            "book": BOOK, "unit": unit,
        })
        check("提交作业返回 job_id", r.status_code == 200 and "job_id" in r.json(), r.text)
        job = wait_job(free_token, r.json()["job_id"])
        check("作业任务完成", job["status"] == "done",
              f"status={job['status']} err={job.get('error')}")
        hw = job.get("result") or {}
        check("免费用户结果被锁定", hw.get("locked") is True, str(hw)[:150])
        check("免费用户看不到逐题解析", hw.get("details") == [], str(hw.get("details"))[:150])
        check("免费用户看不到 AI 评语", hw.get("comment") == "", str(hw.get("comment"))[:150])
        check("免费用户仍能看到总分", "total_score" in hw, str(hw)[:150])

        print("\n=== 会员 ===")
        r = get("/membership/plans", free_token)
        plans = r.json()
        check("套餐列表 3 档", len(plans["plans"]) == 3, r.text)
        check("权益对比非空", len(plans["feature_matrix"]) > 0, r.text)

        r = post("/membership/purchase", free_token, json={"plan": "月卡"})
        check("模拟支付开通月卡", r.status_code == 200 and r.json()["ok"], r.text)
        check("开通后 is_vip=true", r.json()["user"]["is_vip"] is True, r.text)
        r = post("/membership/purchase", free_token, json={"plan": "不存在的套餐"})
        check("未知套餐 -> 400", r.status_code == 400, r.text)

        r = get("/membership/orders", free_token)
        check("订单记录可读", r.status_code == 200 and r.json()["count"] >= 1, r.text)

        print("\n=== 客服留言 ===")
        r = post("/messages", vip_token, json={"content": "接口测试留言"})
        check("提交留言", r.status_code == 200 and r.json()["ok"], r.text)
        r = get("/messages", vip_token)
        check("查看自己的留言", r.status_code == 200 and r.json()["count"] >= 1, r.text)

        print("\n=== 管理后台 ===")
        r = get("/admin/stats", vip_token)
        check("学生访问后台 -> 403", r.status_code == 403, r.text)
        r = get("/admin/stats", admin_token)
        check("管理员拿到概览", r.status_code == 200 and r.json()["user_count"] > 0, r.text)
        r = get("/admin/users", admin_token, params={"q": "student"})
        check("用户搜索", r.status_code == 200 and r.json()["count"] >= 1, r.text)
        r = get("/admin/users", admin_token)
        check("后台用户列表不含密码哈希",
              all("password" not in u for u in r.json()["users"]), "")

        print("\n=== 作业批改（VIP 应能看到解析） ===")
        r = post("/homework/grade", vip_token, json={
            "text": "I go to school yesterday and meet my friend. He is very happy.",
            "book": BOOK, "unit": unit,
        })
        job = wait_job(vip_token, r.json()["job_id"])
        hw = job.get("result") or {}
        check("VIP 结果未锁定", hw.get("locked") is False, str(hw)[:150])
        check("VIP 能看到逐题解析", isinstance(hw.get("details"), list) and len(hw["details"]) > 0,
              str(hw.get("details"))[:150])

    finally:
        drop_free_user()

    print(f"\n{'=' * 46}\n通过 {passed} 项，失败 {failed} 项\n{'=' * 46}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
