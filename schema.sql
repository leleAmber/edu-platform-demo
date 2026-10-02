-- ===========================================================================
-- 课伴AI｜英语课本智能学习助手 —— 数据库结构
-- 适用：MySQL 8.0+ / MariaDB 10.6+
-- 字符集：utf8mb4（支持 emoji），排序规则 utf8mb4_unicode_ci（用户名、邮箱大小写不敏感）
--
-- 使用方式：
--   1) 应用启动时会自动执行等价的 CREATE TABLE IF NOT EXISTS，无需手工建表；
--   2) 也可以由 DBA 手工执行本文件完成建表。
--
-- 关于主键：所有表都用整型自增主键。业务上展示的 U001 / O001 / M001 这类编号
-- 由主键派生（CONCAT('U', LPAD(id, 3, '0'))），不参与唯一性约束。这样并发写入时
-- 由数据库保证唯一，不会出现两条记录抢到同一个编号的情况。
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 用户表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部主键',
  username   VARCHAR(50)     NOT NULL                COMMENT '用户名，唯一，大小写不敏感',
  email      VARCHAR(120)    NOT NULL                COMMENT '注册邮箱，唯一',
  password   VARCHAR(255)    NOT NULL                COMMENT 'PBKDF2-SHA256 哈希，绝不存明文',
  role       VARCHAR(20)     NOT NULL DEFAULT 'student' COMMENT 'student 学生 / admin 管理员',
  vip_until  DATETIME        NULL                    COMMENT '会员到期时间，NULL 表示未开通',
  vip_plan   VARCHAR(20)     NULL                    COMMENT '最近一次开通的套餐名',
  created_at DATETIME        NOT NULL                COMMENT '注册时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username),
  UNIQUE KEY uk_users_email (email),
  KEY idx_users_role (role),
  KEY idx_users_vip_until (vip_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';


-- ---------------------------------------------------------------------------
-- 会员订单表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部主键',
  username   VARCHAR(50)     NOT NULL                COMMENT '下单用户名',
  plan_name  VARCHAR(20)     NOT NULL                COMMENT '套餐名：月卡 / 季卡 / 年卡',
  amount     DECIMAL(10,2)   NOT NULL DEFAULT 0.00   COMMENT '金额，用 DECIMAL 避免浮点误差',
  days       INT UNSIGNED    NOT NULL DEFAULT 0      COMMENT '本次开通天数',
  vip_until  DATETIME        NULL                    COMMENT '本单生效后的会员到期时间',
  status     VARCHAR(20)     NOT NULL DEFAULT '已支付' COMMENT '订单状态',
  pay_method VARCHAR(20)     NOT NULL DEFAULT '模拟支付' COMMENT '支付方式',
  created_at DATETIME        NOT NULL                COMMENT '下单时间',
  PRIMARY KEY (id),
  KEY idx_orders_username (username),
  KEY idx_orders_created_at (created_at),
  KEY idx_orders_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会员订单表';


-- ---------------------------------------------------------------------------
-- 客服留言表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部主键',
  username   VARCHAR(50)     NOT NULL                COMMENT '留言用户',
  content    TEXT            NOT NULL                COMMENT '留言内容',
  is_replied TINYINT(1)      NOT NULL DEFAULT 0      COMMENT '是否已回复：0 未回复 / 1 已回复',
  reply      TEXT            NULL                    COMMENT '管理员回复内容',
  created_at DATETIME        NOT NULL                COMMENT '留言时间',
  replied_at DATETIME        NULL                    COMMENT '回复时间',
  PRIMARY KEY (id),
  KEY idx_messages_created_at (created_at),
  KEY idx_messages_is_replied (is_replied),
  KEY idx_messages_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服留言表';


-- ---------------------------------------------------------------------------
-- 学习记录表
-- 用于首页「最近学习记录」、学情诊断与学习进度图，必须持久化：
-- 学情分析需要跨会话的历史数据才有意义。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learning_records (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部主键',
  username   VARCHAR(50)     NOT NULL                COMMENT '所属用户',
  module     VARCHAR(50)     NOT NULL                COMMENT '学习模块：课本预习 / 作业批改 等',
  unit       VARCHAR(100)    NULL                    COMMENT '学习单元',
  score      INT             NULL                    COMMENT '本次得分',
  level      VARCHAR(20)     NULL                    COMMENT '评级：优秀 / 良好 / 需要提升',
  created_at DATETIME        NOT NULL                COMMENT '记录时间',
  PRIMARY KEY (id),
  KEY idx_records_user_time (username, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学习记录表';


-- ---------------------------------------------------------------------------
-- 题库表
-- 由离线脚本批量生成、页面按题型随机抽取组卷。一题一行：
-- - book 为教材维度（必修一/必修二/必修三/选一/选二/选三/选四），7 本书之间题目隔离；
-- - reading / blank（完形/语法填空）每道题一行，同一篇文章的 passage 会重复存储；
-- - answer 存完整选项文本（不是 A/B/C/D），与现有判分的精确字符串比较一致；
-- - content_hash 为题目归一化文本的 SHA-1，唯一键挡重复。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS question_bank (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内部主键',
  content_hash        CHAR(40)        NOT NULL                COMMENT '题目归一化文本的 SHA-1，去重',
  book                VARCHAR(50)     NULL                    COMMENT '教材：必修一~必修三 / 选一~选四',
  grade               VARCHAR(20)     NOT NULL DEFAULT '高一' COMMENT '年级：高一 / 高二 / 高三',
  module              VARCHAR(20)     NOT NULL                COMMENT '模块：preview / review / mock',
  unit                VARCHAR(100)    NULL                    COMMENT '单元名（preview/review）；mock 为 NULL',
  qtype               VARCHAR(20)     NOT NULL                COMMENT '题型：choice/reading/seven_five/cloze/grammar_blank/writing_practical/writing_continuation',
  passage             TEXT            NULL                    COMMENT '阅读/完形/语法填空/七选五的文章',
  question            TEXT            NOT NULL                COMMENT '题干',
  options             TEXT            NULL                    COMMENT 'JSON 数组（选择题/带选项的填空）',
  answer              TEXT            NULL                    COMMENT '正确答案（选择题存完整选项文本）',
  explanation         TEXT            NULL                    COMMENT '中文解析',
  writing_prompt      TEXT            NULL                    COMMENT '写作题题目',
  writing_requirements TEXT           NULL                    COMMENT 'JSON 数组（写作要求）',
  score               INT             NOT NULL DEFAULT 1      COMMENT '分值（组卷用）',
  difficulty          TINYINT         NOT NULL DEFAULT 2      COMMENT '难度 1~5',
  status              TINYINT(1)      NOT NULL DEFAULT 1      COMMENT '1 启用 / 0 停用',
  source              VARCHAR(20)     NOT NULL DEFAULT 'llm'  COMMENT '来源：llm / manual',
  created_at          DATETIME        NOT NULL                COMMENT '入库时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_qb_hash (content_hash),
  KEY idx_qb_book (book),
  KEY idx_qb_grade_module (grade, module),
  KEY idx_qb_unit (unit),
  KEY idx_qb_qtype (qtype),
  KEY idx_qb_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题库表';
