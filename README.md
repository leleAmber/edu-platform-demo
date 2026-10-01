# 课伴AI｜英语课本智能学习助手

面向初高中学生的英语课本学习 Web 应用，覆盖 **课本预习复习 → AI 作业批改 → 模拟试卷 → 学情诊断 → 会员开通 → 管理后台** 的完整闭环。

技术栈为 Python + Streamlit + MySQL，数据通过 SQLAlchemy 连接池持久化到 MySQL，AI 批改与学情分析为本地规则模拟（**不依赖外部大模型 API**）。

`index.html` 保留为早期交互与视觉稿参考，当前可运行入口是 `app.py`。

---

## 目录

- [功能总览](#功能总览)
- [快速开始](#快速开始)
- [演示账号](#演示账号)
- [页面与访问路径](#页面与访问路径)
- [目录结构](#目录结构)
- [核心模块说明](#核心模块说明)
- [模拟 AI 的实现方式](#模拟-ai-的实现方式)
- [会员体系与权限拦截](#会员体系与权限拦截)
- [邮箱验证码注册](#邮箱验证码注册)
- [数据存储](#数据存储)
- [常见问题](#常见问题)
- [上线前需要补齐的部分](#上线前需要补齐的部分)

---

## 功能总览

### 学生端

| 模块 | 功能 |
| --- | --- |
| 登录注册 | 账号密码登录、邮箱验证码注册、记住密码、忘记密码提示 |
| 首页 | 单元选择、4 张功能入口卡片、今日学习建议、最近学习记录 |
| 课本预习 | 课文节选、AI 长难句解析（主干 / 修饰 / 翻译）、6 张核心词汇卡、5 道预习自测、3 天预习计划 |
| 课本复习 | 词汇 / 语法 / 语篇三模块掌握度、单词掌握统计、5 道单元练习、7 天错题巩固计划 |
| 作业中心 | 左右分栏：左栏录入作业，右栏展示批改结果（免费版只给总分，VIP 给逐句解析） |
| 模拟试卷 | **VIP 专属**。阅读理解 / 语言运用 / 书面写作三板块，交卷自动评分并给出评语 |
| 会员中心 | 会员状态卡片、月卡 / 季卡 / 年卡三档套餐、模拟支付确认弹窗、权益对比表 |
| 学情诊断 | **VIP 专属**。四维能力雷达图、诊断摘要与改进建议、错题归因占比、学习进度统计图 |
| 客服留言 | 侧边栏入口，提交留言给管理员 |

### 管理端

| 模块 | 功能 |
| --- | --- |
| 用户管理 | 按用户名 / 邮箱搜索，表格展示用户名、邮箱、角色、VIP 到期时间、注册时间 |
| 消费记录 | 总订单数、累计收入、已支付订单数统计卡片 + 订单明细表 |
| 客服留言 | 留言统计、留言列表表格、逐条回复并标记已回复 |

### 内置教材内容

覆盖人教版必修一 4 个单元，每个单元均含课文选段、长难句解析、核心词汇、语法 / 语篇知识点与 10 道练习题：

- `Unit1 Teenage Life` — 校园生活 · 社团与时间管理
- `Unit2 Travelling Around` — 旅行 · 行程规划与文化遗产
- `Unit3 Sports and Fitness` — 运动与健康 · 坚持与团队精神
- `Unit4 Natural Disasters` — 自然灾害 · 救援与重建

---

## 快速开始

**环境要求**：Python 3.9+、MySQL 8.0+、**Streamlit 1.64+**
（开发与验证环境：Python 3.13 / Streamlit 1.64 / Plotly 7.1 / pandas 3.0 / MySQL 8.4.8）

> ⚠️ **Streamlit 版本必须对上。** 代码用了 `st.tabs(default=..., key=...)`、`width="stretch"` 等较新的 API，这些参数在 1.55 之前并不存在。如果直接拿系统里已有的旧版 Streamlit 跑，会在启动页（`app.py` 的登录/注册标签页）直接抛 `TypeError: LayoutsMixin.tabs() got an unexpected keyword argument 'key'`。**务必用下面第 3 步的虚拟环境安装依赖，不要复用 Anaconda 等环境里自带的 Streamlit。**

### 第 1 步：准备数据库

先建库和专用账号。**不要用 root 跑应用**，给它单独开一个只有必要权限的账号：

```sql
CREATE DATABASE IF NOT EXISTS keban_ai
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'keban_app'@'localhost' IDENTIFIED BY '换成你的密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON keban_ai.* TO 'keban_app'@'localhost';
FLUSH PRIVILEGES;
```

表结构**不需要手工创建**——应用首次连接时会自动执行等价的 `CREATE TABLE IF NOT EXISTS`。也可以由 DBA 手工执行项目根目录的 `schema.sql`。

### 第 2 步：填写连接信息

在 `.streamlit/secrets.toml` 中配置（也可以用同名环境变量，**环境变量优先级更高**）：

```toml
DB_HOST = '127.0.0.1'
DB_PORT = '3306'
DB_USER = 'keban_app'
DB_PASSWORD = '换成你的密码'
DB_NAME = 'keban_ai'
DB_SEED_DEMO = '1'    # 生产环境必须设为 '0'，关闭代码内置演示账号的写入
```

### 第 3 步：安装依赖并启动

```bash
cd edu-platform-demo

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

> 端口被占用时可指定：`streamlit run app.py --server.port 8502`

**装了 Anaconda / 全局装过 Streamlit 的机器要注意**：旧版 Streamlit 可能抢先生效，导致启动就 `TypeError`。先确认版本，或干脆不激活环境、直接用 venv 里的解释器启动：

```bash
python -c "import streamlit; print(streamlit.__version__)"   # 必须 >= 1.64

# Windows：不激活也能跑，最不容易出环境串味
.venv\Scripts\python.exe -m streamlit run app.py
```

**连不上数据库怎么办？** 在项目目录执行下面这行，会返回具体的失败原因（认证失败 / 库不存在 / 网络不通）：

```bash
python -c "from core import database; print(database.health_check())"
```

---

## 演示账号

| 角色 | 用户名 | 密码 | 可见菜单 |
| --- | --- | --- | --- |
| 学生 | `student` | `123456` | 首页、课本预习、课本复习、作业中心、模拟试卷、会员中心、学情诊断 |
| 管理员 | `admin` | `123456` | 首页、用户管理、消费记录、客服留言 |

两个账号的初始 `vip_until` 都是 `null`（免费版）。用 `student` 登录后到「会员中心」走一次模拟支付，即可解锁模拟试卷与学情诊断。

> 当 `users` 表为空时（首次连接数据库），应用会自动写入这两个账号，密码以 PBKDF2-SHA256 哈希形式存储，不落明文。把 `DB_SEED_DEMO` 设为 `'0'` 可关闭这个行为——**商用部署建议关闭，并改掉初始密码**。

---

## 页面与访问路径

侧边导航由角色决定，菜单名称与访问路径如下（路径由文件名自动生成）：

| 菜单 | 文件 | 访问路径 | 可见角色 |
| --- | --- | --- | --- |
| 首页 | `pages/1_home.py` | `/` | 全部 |
| 课本预习 | `pages/2_preview.py` | `/preview` | 学生 |
| 课本复习 | `pages/3_review.py` | `/review` | 学生 |
| 作业中心 | `pages/4_homework.py` | `/homework` | 学生 |
| 模拟试卷 | `pages/5_mock_exam.py` | `/mock_exam` | 学生（VIP） |
| 会员中心 | `pages/6_membership.py` | `/membership` | 学生 |
| 学情诊断 | `pages/7_diagnosis.py` | `/diagnosis` | 学生（VIP） |
| 用户管理 | `pages/8_admin.py` | `/admin-users` | 管理员 |
| 消费记录 | `pages/8_admin.py` | `/admin-orders` | 管理员 |
| 客服留言 | `pages/8_admin.py` | `/admin-messages` | 管理员 |

管理端的三个菜单项复用同一个页面文件，靠 `url_path` 区分，进入后自动展开对应 tab。

未登录时直接访问上述任何路径都不会泄露内容：每个页面入口都有登录守卫，会中止渲染并提示返回登录。

---

## 目录结构

```
edu-platform-demo/
├── app.py                      # 入口：全局初始化、登录/注册页、按角色组装侧边导航
├── requirements.txt            # streamlit / plotly / pandas / SQLAlchemy / PyMySQL
├── schema.sql                  # 建表 DDL（应用会自动建表，此文件供 DBA 手工执行）
├── README.md
├── index.html                  # 早期交互视觉稿（仅参考，不参与运行）
├── .streamlit/
│   ├── config.toml             # 本地运行配置（关闭统计上报、保存即重载），可提交
│   └── secrets.toml            # 数据库 + SMTP 配置（含密钥，已被 .gitignore 忽略，不要提交）
│
├── core/                       # 业务逻辑层：页面只能调用这里的方法
│   ├── __init__.py
│   ├── database.py             # MySQL 连接池、建表、全部 CRUD
│   ├── auth.py                 # 登录、注册、邮箱验证码、会话用户
│   ├── vip.py                  # VIP 判定、套餐、模拟支付、权限拦截弹窗
│   └── tutor_ai.py             # 模拟 AI：教材内容、作业批改、掌握度、学习计划、错题归因、阅卷
│
├── components/                 # 可复用 UI 组件层
│   ├── __init__.py             # flash 提示队列、跨 rerun 输入回填、隐藏侧边栏样式
│   ├── user_menu.py            # 侧边栏用户卡片、会员标签、退出登录
│   ├── cards.py                # 功能入口卡片、单词卡片、状态标签
│   └── charts.py               # 四维能力雷达图、学习进度统计图（plotly）
│
├── pages/                      # 页面层：只负责调用组件、渲染 UI、捕获交互
│   ├── 1_home.py               # 首页
│   ├── 2_preview.py            # 课本预习
│   ├── 3_review.py             # 课本复习
│   ├── 4_homework.py           # 作业中心
│   ├── 5_mock_exam.py          # 模拟试卷（VIP）
│   ├── 6_membership.py         # 会员中心
│   ├── 7_diagnosis.py          # 学情诊断（VIP）
│   └── 8_admin.py              # 管理后台（复用为 3 个菜单）
│
└── (数据库)                     # 数据存放在 MySQL 中，不在项目目录内
```

### 分层约定

1. **页面不写业务逻辑**：所有数据读写、计算、权限判断都调用 `core/` 中的函数。
2. **数据读写只走 `core/database.py`**：页面不直接写 SQL，也不直接建连接。
3. **VIP 校验统一走 `core/vip.check_vip_permission()`**：页面里不出现硬编码的角色判断。
4. **状态存在 `st.session_state`**：当前单元、表单回填等切页面不丢失。需要跨会话保留的数据（学习记录、会员状态）一律落库。

---

## 核心模块说明

### core/database.py — 数据访问层

| 函数 | 说明 |
| --- | --- |
| `health_check()` | 探测数据库可用性，返回 `(是否连通, 说明文字)`，用于排查连接问题 |
| `init_schema()` | 建表并写入初始账号，幂等，可重复调用 |
| `get_db_config()` | 组装连接配置（环境变量优先，其次 `st.secrets`） |
| `get_user_by_username(username)` / `get_user_by_email(email)` | 按用户名 / 邮箱查用户，大小写不敏感 |
| `add_new_user(user_info)` | 新增注册用户，用户名重复返回 `None` |
| `update_user(username, update_dict)` | 更新用户信息（开通会员写入 `vip_until` 等） |
| `get_all_users()` | 全部用户列表 |
| `add_order(order_info)` / `get_all_orders()` | 新增 / 读取会员订单（按时间倒序） |
| `add_message(msg_info)` / `get_all_messages()` | 新增 / 读取客服留言（按时间倒序） |
| `update_message(msg_id, reply_content)` | 管理员回复留言，写入 `reply` 并把 `is_replied` 置为 `true` |
| `add_learning_record(username, record)` / `get_learning_records(username, limit)` | 学习记录，持久化到数据库，最新的排在最前 |
| `hash_password(pwd)` / `verify_password(pwd, stored)` | 密码哈希与校验 |

### core/auth.py — 认证层

| 函数 | 说明 |
| --- | --- |
| `login(username, password)` | 校验账号密码，成功把用户写入 `st.session_state["current_user"]`，返回 `bool` |
| `register(username, email, password, confirm_pwd, code)` | 全部校验通过才建号，返回 `(是否成功, 提示文字)` |
| `logout()` | 清空登录态、验证码缓存与 VIP 拦截标记 |
| `get_current_user()` | 读取当前登录用户，未登录返回 `None` |
| `refresh_current_user()` | 从数据表重新同步会话用户（支付后刷新会员状态用） |
| `require_login()` | 页面级登录守卫，未登录直接中止渲染 |
| `send_verification_code(email)` | 发送验证码，返回 `(是否成功, 提示文字, 演示验证码)` |
| `verify_code(email, code)` | 校验验证码，成功即失效，返回 `(是否通过, 提示文字)` |
| `get_smtp_config()` | 组装 SMTP 配置，字段缺失时返回 `None` |

注册校验顺序：用户名 2~20 字符且不含空格、用户名未被占用、邮箱格式正确且未被注册、密码 ≥6 位、两次密码一致、验证码正确。

### core/vip.py — 会员体系

| 函数 | 说明 |
| --- | --- |
| `is_vip(user)` | 解析 `vip_until` 与当前时间比较，返回布尔值 |
| `vip_until_text(user)` | 到期时间文案，未开通返回「暂未开通」 |
| `process_payment(username, plan_name)` | 模拟支付：计算到期时间 → 更新用户 → 写入订单 |
| `check_vip_permission()` | 权限拦截。会员返回 `True`；非会员弹出拦截弹窗并返回 `False` |

### core/tutor_ai.py — 模拟 AI

| 函数 | 说明 |
| --- | --- |
| `get_unit_content(unit)` | 取指定单元的课文、词汇、练习、知识点 |
| `grade_quiz(unit, quiz_type, answers)` | 批改预习 / 复习练习，返回得分与逐题解析 |
| `homework_correct(text, include_details=None)` | 作业批改。`include_details` 为 `None` 时按会员状态自动决定返回粒度 |
| `get_mastery_score(seed=None, base=None)` | 生成 0~100 掌握分与评级 |
| `mastery_level(score)` / `level_tag_type(level)` | 分数转评级、评级转标签样式 |
| `gen_study_plan(plan_type, unit=None)` | `preview` 生成 3 天预习计划，`review` 生成 7 天错题巩固计划 |
| `error_analysis(seed=None)` | 四维能力分数 + 错题占比 + 优势 / 薄弱维度 + 改进建议 |
| `get_mock_exam()` / `grade_mock_exam(answers, writing_text)` | 取模拟试卷、阅卷评分 |

### components/

| 组件 | 说明 |
| --- | --- |
| `user_menu.render_sidebar_user()` | 侧边栏用户卡片：用户名、角色、VIP 金色标签 / 灰色「免费版」标签、退出登录 |
| `cards.func_card(...)` | 功能入口卡片，支持右上角状态标签与跳转前写入状态 |
| `cards.knowledge_card(...)` | 单词卡片：单词、词性、中文释义、例句 |
| `cards.status_tag(text, tag_type)` | 状态标签，`tag_type` 可取 `vip` / `success` / `warn` / `danger` / `info` / `plain` |
| `charts.render_ability_radar(...)` | 四维能力雷达图（词汇能力 / 句法语法 / 语篇理解 / 写作输出） |
| `charts.render_progress_chart(records)` | 学习进度柱状图，含优秀线，无数据时展示空状态 |
| `flash(msg)` / `show_flash()` | 跨 rerun 的提示队列，保证 `st.toast` 在页面刷新后仍能弹出 |

---

## 模拟 AI 的实现方式

全部为本地规则 + 可复现的随机模拟，**同一份输入任何时候结果一致**（页面刷新不会让分数乱跳）。

### 作业批改

- 先按句末标点与换行断句，再对每个句子依次套用 **15 条正则规则**，最后补一条句末标点检查。
- 规则覆盖：`i` 未大写、`a` / `an` 误用、第三人称单数、不可数名词复数、比较级重复（`more better`）、`although…but` 与 `because…so` 连用、`very` 修饰动词、`discuss about`、`there have`、`make sb to do`、`In my opinion, I think`、`can not`、`am agree`、`yesterday` 搭配非过去时。
- 评分：每有一句存在错误扣 8 分，最低 40 分；`right_count` / `wrong_count` 按句子统计。
- 返回粒度：免费用户只拿到 `total_score` / `right_count` / `wrong_count`；VIP 额外拿到 `details`（原句、错误类型、修改后句子、错误解析）、`error_types` 汇总与 `comment` 评语。

### 掌握度评分

- 评级规则：≥85 **优秀**，70~84 **良好**，＜70 **需要提升**。
- 传入客观题得分时，掌握分在客观分基础上小幅浮动（-6 ~ +8），让评估结果与作答表现相关而非纯随机。

### 学情诊断

- 以学习记录的平均分为基准（没有记录时取 62~82 的随机基线），四维各自做不同幅度偏移，因此**练得越多、诊断越贴合实际**。
- 随机种子由「用户名 + 记录条数 + 记录总分」决定，同一状态下刷新页面结果不变。
- 错题占比与能力分反向关联：能力越弱的维度，错题占比越高，保证雷达图与归因标签互相印证。

### 模拟试卷

- 满分 100：阅读理解 3 题 × 15 分 + 语言运用 3 题 × 10 分 + 书面写作 25 分。
- 写作按四个角度评分：词数（2/4/6/8 分）、句子数量（1/3/5 分）、连接词使用（0/3/6 分）、语法错误数量（0/3/6 分），上限 25 分。

---

## 会员体系与权限拦截

| 套餐 | 价格 | 有效期 |
| --- | --- | --- |
| 月卡 | ¥10 | 30 天 |
| 季卡 | ¥20 | 90 天 |
| 年卡 | ¥60 | 365 天（标记【推荐】） |

- **续费顺延**：已开通会员再次购买时，从原到期时间往后叠加，不浪费剩余天数。
- **模拟支付**：`process_payment()` 计算到期时间 → 更新用户 `vip_until` → 写入订单 → 同步会话用户，页面立即刷新会员状态。
- **权限拦截**：进入模拟试卷 / 学情诊断时调用 `check_vip_permission()`。非会员弹出「VIP专属功能」弹窗（【取消】/【前往会员中心】）；取消后页面展示升级占位面板而非空白页，占位面板同样带「前往会员中心」入口。

---

## 邮箱验证码注册

验证码通过项目已有的 `.streamlit/secrets.toml` 配置发送，应用读取以下字段：

| 字段 | 说明 |
| --- | --- |
| `AUTH_OTP_SECRET` | 对验证码做 HMAC-SHA256 摘要用的密钥，数据里不存明文验证码 |
| `SMTP_HOST` / `SMTP_PORT` | 发件服务器地址与端口 |
| `SMTP_USE_SSL` | `1` 走 SSL（163 邮箱常用 465 端口），`0` 走 STARTTLS |
| `SMTP_LOGIN` / `SMTP_PASSWORD` | 发件邮箱账号与 SMTP 授权码 |
| `SMTP_SENDER_EMAIL` | 发件人地址，缺省时用 `SMTP_LOGIN` |
| `AUTH_DEV_MODE` | 设为 `1` 进入本地演示模式：不真实发信，固定验证码 `123456` 并自动填入输入框 |

**安全规则**：验证码 10 分钟过期、同一邮箱 60 秒内只能发一次、最多校验 5 次、校验成功后立即失效。验证码只保存在会话内存中，不写入磁盘。

**发送失败处理**：若网络不通或 SMTP 认证失败，页面只提示失败原因并建议重试，**不会**把验证码显示出来；同时作废本次验证码并清除限流记录，用户可以立即重试而不必等满 60 秒。

验证码只在 `AUTH_DEV_MODE = 1` 的本地演示模式下才会回显（固定 `123456` 并自动填入），这是唯一会跳过真实发信的分支。

---

## 数据存储

数据存放在 MySQL 数据库中，共 4 张表。完整 DDL 见项目根目录的 `schema.sql`；应用首次连接时会自动执行等价的 `CREATE TABLE IF NOT EXISTS`，无需手工建表。

### 表结构

**users 用户表**

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | BIGINT UNSIGNED | 自增主键 |
| `username` | VARCHAR(50) | 用户名，**唯一索引** |
| `email` | VARCHAR(120) | 邮箱，**唯一索引** |
| `password` | VARCHAR(255) | PBKDF2-SHA256 哈希，绝不存明文 |
| `role` | VARCHAR(20) | `student` 学生 / `admin` 管理员 |
| `vip_until` | DATETIME | 会员到期时间，`NULL` 表示未开通 |
| `vip_plan` | VARCHAR(20) | 最近一次开通的套餐名 |
| `created_at` | DATETIME | 注册时间 |

**orders 订单表** — 关注 `amount` 用的是 **DECIMAL(10,2)** 而不是浮点数：金额用 float 会出现 `0.1 + 0.2 ≠ 0.3` 这类误差，商用系统必须用定点小数。

**messages 留言表** — `content` 留言内容、`is_replied` 是否已回复、`reply` 回复内容、`replied_at` 回复时间。

**learning_records 学习记录表** — `module` 学习模块、`unit` 学习单元、`score` 得分、`level` 评级。

### 关于主键：为什么不用 U001 直接当主键

所有表都用**整型自增主键**，页面上展示的 `U001` / `O001` / `M001` 是**从主键派生**出来的（`CONCAT('U', LPAD(id, 3, '0'))`），不参与唯一性约束。

原因是并发安全：如果由应用自己算编号（"查出最大的 U003，下一个就是 U004"），两个用户同时注册会算出同一个号，直接冲突。交给数据库自增主键，这个竞态就不存在了。

### 索引

按实际查询模式建了索引，避免数据量上来后全表扫描：

| 表 | 索引 | 用途 |
| --- | --- | --- |
| `users` | `uk_users_username`（唯一） | 登录时按用户名查 |
| `users` | `uk_users_email`（唯一） | 注册时查重 |
| `users` | `idx_users_vip_until` | 统计会员 |
| `orders` | `idx_orders_created_at` | 后台按时间倒序取订单 |
| `orders` | `idx_orders_username` | 按用户查订单 |
| `messages` | `idx_messages_is_replied` | 后台统计待回复留言 |
| `learning_records` | `idx_records_user_time`（联合） | 按用户 + 时间取学习记录 |

### 字符集与排序规则

`utf8mb4` + `utf8mb4_unicode_ci`。前者支持 emoji，后者让**用户名与邮箱的比较天然大小写不敏感**——数据库会把 `Student` 和 `student` 判为重复，应用层不需要额外做大小写归一。

### 重置数据

```sql
-- 清空某个用户的学习记录
DELETE FROM learning_records WHERE username = 'student';

-- 恢复初始状态：删表后重启应用，会自动重建并写入初始账号
DROP TABLE IF EXISTS users, orders, messages, learning_records;
```

---

## 常见问题

**Q：启动后侧边栏没有菜单？**
未登录时侧边栏是隐藏的。先登录，登录后会按角色渲染导航。

**Q：`student` 登录后看不到「模拟试卷」内容？**
模拟试卷和学情诊断是 VIP 专属。到「会员中心」选任意套餐点「立即开通」，在确认弹窗里点「确认支付」即可（模拟支付，不产生真实扣款）。

**Q：点「获取验证码」提示发送失败？**
检查 `.streamlit/secrets.toml` 里的 `SMTP_HOST` / `SMTP_LOGIN` / `SMTP_PASSWORD` 是否正确、网络能否访问 smtp.163.com。常见原因是发件邮箱把外部收件地址判为垃圾邮件而拒收，换个收件邮箱再试。发送失败时页面**只报错、不会回显验证码**（这是刻意设计：验证码一旦显示在页面上，等于任何人都能注册）。想彻底跳过发信，把 `AUTH_DEV_MODE` 设为 `1`（**仅限本地调试，生产环境必须为 `0`**）。

**Q：注册时提示「请先点击获取验证码」？**
验证码只保存在会话内存里，刷新页面或重启服务后需要重新获取。

**Q：连不上数据库 / 提示数据库配置缺失？**
先跑一下连通性自检：

```bash
.venv/Scripts/python -c "from core import database; print(database.health_check())"
```

返回 `(False, '...')` 时看第二个元素里的错误原因：`Access denied` 是账号密码不对，`Can't connect` 是 MySQL 没启动或端口不通，`Unknown database` 是库还没建。确认 `.streamlit/secrets.toml` 里的 `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` 与实际部署一致。

**Q：想恢复初始状态？**
在 MySQL 里删表后重启应用，会自动重建并写入初始账号：

```sql
DROP TABLE IF EXISTS users, orders, messages, learning_records;
```

**Q：端口 8501 被占用？**
`streamlit run app.py --server.port 8502`

---

## 上线前需要补齐的部分

数据存储已经换成真实 MySQL，**用户、订单、留言、学习记录都会持久化**。但要让这套代码真正扛住线上流量，下面几项还需要补齐：

### 必须做

1. **教材内容**：`core/tutor_ai.py` 中的课文为贴合单元主题的改编选段，需替换为**正版授权**的教材内容，否则有版权风险。
2. **AI 批改与分析**：现在是本地正则规则，需接入真实大模型服务才能获得语义级批改能力。
3. **支付**：现在是模拟支付，页面上点「确认支付」并不会产生任何真实扣款。需接入微信 / 支付宝的商户后端，并**以支付平台的异步回调为准**写入订单状态——不能信任前端传来的"已支付"。
4. **演示账号**：生产环境必须把 `DB_SEED_DEMO` 设为 `0`，禁用 `student` / `admin` 两个固定账号（它们的密码写在代码里，等于是公开的），并改用一次性初始化脚本创建管理员账号。

### 数据库运维

5. **备份**：MySQL 的 `mysqldump` 做每日全量 + binlog 做增量，并**实际演练一次恢复流程**——没恢复成功过的备份不算备份。云数据库（阿里云 RDS 等）可以直接打开自动备份。
6. **表结构变更（迁移）**：现在靠 `CREATE TABLE IF NOT EXISTS` 自动建表，它只能建新表、**不能改已有表**。后续加字段要引入 Alembic 之类的迁移工具，否则线上加个字段就得手工敲 SQL。
7. **连接与权限**：应用账号只授予 `SELECT / INSERT / UPDATE / DELETE` 与必要的 DDL 权限，**绝不用 root 跑应用**；MySQL 只监听 `127.0.0.1`（或内网地址），3306 端口不对公网开放。
8. **监控与告警**：连接池耗尽、慢查询、磁盘占用需要有告警，不能等用户反馈才发现。

### 账号与安全

9. **登录风控**：补充登录失败次数限制（锁定 / 验证码）、验证码发送频率限制、会话过期时间。
10. **密钥管理**：`.streamlit/secrets.toml` 不入库，线上用环境变量或密钥管理服务注入；`AUTH_OTP_SECRET` 要是随机生成的长串，不能用默认值。定期更换数据库密码与邮箱授权码。
