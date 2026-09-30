import 'dotenv/config';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import fs from 'node:fs';
import bcrypt from 'bcryptjs';
import { DatabaseSync } from 'node:sqlite';
import nodemailer from 'nodemailer';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 3000);
const appUrl = process.env.APP_URL || `http://localhost:${port}`;
const dbFile = path.resolve(__dirname, process.env.DB_FILE || './data/keban.sqlite');
fs.mkdirSync(path.dirname(dbFile), { recursive: true });
const db = new DatabaseSync(dbFile);
db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    email_verified_at TEXT,
    vip_until TEXT,
    created_at TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS email_verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
  CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
  CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
  CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'cny',
    provider TEXT NOT NULL,
    provider_session_id TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    paid_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
  CREATE TABLE IF NOT EXISTS support_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    reply TEXT,
    replied_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
  CREATE TABLE IF NOT EXISTS learning_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    score INTEGER,
    payload TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
`);

const now = () => new Date().toISOString();
const addDays = (days) => new Date(Date.now() + days * 86400000).toISOString();
const token = (size = 32) => crypto.randomBytes(size).toString('hex');
const sha256 = (value) => crypto.createHash('sha256').update(value).digest('hex');
const validEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
const plans = {
  '月卡': { amount: 1000, days: 30 },
  '季卡': { amount: 2000, days: 90 },
  '年卡': { amount: 6000, days: 365 }
};

function seedAdmin() {
  const username = process.env.ADMIN_USERNAME || 'admin';
  const email = process.env.ADMIN_EMAIL || 'admin@example.com';
  const password = process.env.ADMIN_PASSWORD || 'ChangeMe_admin_123!';
  const existing = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (!existing) {
    db.prepare(`INSERT INTO users (username,email,password_hash,role,email_verified_at,created_at) VALUES (?,?,?,?,?,?)`)
      .run(username, email.toLowerCase(), bcrypt.hashSync(password, 12), 'admin', now(), now());
    console.log(`[seed] admin account: ${username} / ${password}`);
  }
}
seedAdmin();

let mailer = null;
if (process.env.SMTP_HOST && process.env.SMTP_USER && process.env.SMTP_PASS) {
  mailer = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT || 587),
    secure: process.env.SMTP_SECURE === 'true',
    auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
  });
}

async function sendMail({ to, subject, text }) {
  if (!mailer) {
    if (process.env.NODE_ENV !== 'production' && process.env.ALLOW_DEV_EMAIL_CODE !== 'false') {
      console.log(`[dev-mail] to=${to} subject=${subject}\n${text}`);
      return false;
    }
    throw new Error('邮件服务未配置');
  }
  await mailer.sendMail({ from: process.env.MAIL_FROM || process.env.SMTP_USER, to, subject, text });
  return true;
}

function serializeUser(user) {
  if (!user) return null;
  return {
    id: user.id, username: user.username, email: user.email, role: user.role,
    emailVerified: Boolean(user.email_verified_at), vipUntil: user.vip_until,
    createdAt: user.created_at
  };
}

function issueSession(res, userId) {
  const raw = token();
  const days = Number(process.env.SESSION_DAYS || 7);
  db.prepare('INSERT INTO sessions (user_id,token_hash,expires_at,created_at) VALUES (?,?,?,?)')
    .run(userId, sha256(raw), addDays(days), now());
  res.cookie('sid', raw, {
    httpOnly: true, sameSite: 'lax', secure: process.env.COOKIE_SECURE === 'true',
    maxAge: days * 86400000, path: '/'
  });
}

function clearSession(req, res) {
  const raw = req.cookies?.sid;
  if (raw) db.prepare('DELETE FROM sessions WHERE token_hash = ?').run(sha256(raw));
  res.clearCookie('sid', { httpOnly: true, sameSite: 'lax', secure: process.env.COOKIE_SECURE === 'true', path: '/' });
}

function currentUser(req) {
  const raw = req.cookies?.sid;
  if (!raw) return null;
  const row = db.prepare(`SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?`).get(sha256(raw), now());
  return row || null;
}

function requireAuth(req, res, next) {
  const user = currentUser(req);
  if (!user) return res.status(401).json({ error: '请先登录' });
  req.user = user;
  next();
}

function requireAdmin(req, res, next) {
  if (req.user.role !== 'admin') return res.status(403).json({ error: '无权限' });
  next();
}

function grantVip(order) {
  const user = db.prepare('SELECT * FROM users WHERE id=?').get(order.user_id);
  const base = user.vip_until && new Date(user.vip_until) > new Date() ? new Date(user.vip_until) : new Date();
  base.setDate(base.getDate() + plans[order.plan].days);
  const paidAt = now();
  db.prepare('UPDATE orders SET status=?, paid_at=? WHERE id=?').run('paid', paidAt, order.id);
  db.prepare('UPDATE users SET vip_until=? WHERE id=?').run(base.toISOString(), user.id);
}

const app = express();
app.disable('x-powered-by');
app.use((req, res, next) => {
  if (req.path === '/api/webhooks/stripe') return next();
  return express.json({ limit: '1mb' })(req, res, next);
});
app.use(express.urlencoded({ extended: false }));
app.use((req, res, next) => {
  const cookie = req.headers.cookie || '';
  req.cookies = Object.fromEntries(cookie.split(';').filter(Boolean).map((part) => {
    const index = part.indexOf('=');
    return [part.slice(0, index).trim(), decodeURIComponent(part.slice(index + 1).trim())];
  }));
  next();
});

app.get('/api/health', (_req, res) => res.json({ ok: true, service: 'keban-ai', time: now() }));

app.post('/api/auth/register', async (req, res) => {
  const username = String(req.body.username || '').trim();
  const email = String(req.body.email || '').trim().toLowerCase();
  const password = String(req.body.password || '');
  if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]{2,20}$/.test(username)) return res.status(400).json({ error: '用户名需为2-20位字母、数字、下划线或中文' });
  if (!validEmail(email)) return res.status(400).json({ error: '邮箱格式不正确' });
  if (password.length < 8) return res.status(400).json({ error: '密码至少8位' });
  if (db.prepare('SELECT id FROM users WHERE username=? OR email=?').get(username, email)) return res.status(409).json({ error: '用户名或邮箱已存在' });
  const info = db.prepare('INSERT INTO users (username,email,password_hash,created_at) VALUES (?,?,?,?)').run(username, email, bcrypt.hashSync(password, 12), now());
  const code = String(crypto.randomInt(100000, 1000000));
  db.prepare('INSERT INTO email_verifications (user_id,purpose,code_hash,expires_at,created_at) VALUES (?,?,?,?,?)')
    .run(info.lastInsertRowid, 'register', sha256(code), addDays(1 / 1440), now());
  try {
    const sent = await sendMail({ to: email, subject: '课伴AI邮箱验证码', text: `你的课伴AI验证码是 ${code}，10分钟内有效。` });
    const payload = { message: '注册成功，请查收邮箱验证码', emailSent: sent };
    if (!sent && process.env.NODE_ENV !== 'production' && process.env.ALLOW_DEV_EMAIL_CODE !== 'false') payload.devCode = code;
    return res.status(201).json(payload);
  } catch (error) {
    db.prepare('DELETE FROM users WHERE id=?').run(info.lastInsertRowid);
    return res.status(503).json({ error: error.message });
  }
});

app.post('/api/auth/verify-email', (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const code = String(req.body.code || '').trim();
  const user = db.prepare('SELECT * FROM users WHERE email=?').get(email);
  const record = user && db.prepare(`SELECT * FROM email_verifications WHERE user_id=? AND purpose='register' AND consumed_at IS NULL AND expires_at>? ORDER BY id DESC`).get(user.id, now());
  if (!user || !record || !/^[0-9]{6}$/.test(code) || sha256(code) !== record.code_hash) return res.status(400).json({ error: '验证码错误或已过期' });
  db.prepare('UPDATE email_verifications SET consumed_at=? WHERE id=?').run(now(), record.id);
  db.prepare('UPDATE users SET email_verified_at=? WHERE id=?').run(now(), user.id);
  issueSession(res, user.id);
  res.json({ user: serializeUser(db.prepare('SELECT * FROM users WHERE id=?').get(user.id)) });
});

app.post('/api/auth/resend-verification', async (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const user = db.prepare('SELECT * FROM users WHERE email=?').get(email);
  if (!user) return res.status(404).json({ error: '邮箱未注册' });
  if (user.email_verified_at) return res.status(400).json({ error: '邮箱已经验证' });
  const code = String(crypto.randomInt(100000, 1000000));
  db.prepare('INSERT INTO email_verifications (user_id,purpose,code_hash,expires_at,created_at) VALUES (?,?,?,?,?)').run(user.id, 'register', sha256(code), addDays(1 / 1440), now());
  try {
    const sent = await sendMail({ to: email, subject: '课伴AI邮箱验证码', text: `你的课伴AI验证码是 ${code}，10分钟内有效。` });
    const payload = { message: '验证码已发送', emailSent: sent };
    if (!sent && process.env.NODE_ENV !== 'production' && process.env.ALLOW_DEV_EMAIL_CODE !== 'false') payload.devCode = code;
    res.json(payload);
  } catch (error) { res.status(503).json({ error: error.message }); }
});

app.post('/api/auth/login', (req, res) => {
  const username = String(req.body.username || '').trim();
  const password = String(req.body.password || '');
  const user = db.prepare('SELECT * FROM users WHERE username=? OR email=?').get(username, username.toLowerCase());
  if (!user || !bcrypt.compareSync(password, user.password_hash)) return res.status(401).json({ error: '账号或密码错误' });
  if (!user.email_verified_at) return res.status(403).json({ error: '请先完成邮箱验证', verificationRequired: true, email: user.email });
  issueSession(res, user.id);
  res.json({ user: serializeUser(user) });
});

app.post('/api/auth/logout', (req, res) => { clearSession(req, res); res.json({ ok: true }); });
app.get('/api/auth/me', (req, res) => res.json({ user: serializeUser(currentUser(req)) }));

app.post('/api/auth/forgot-password', async (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const user = db.prepare('SELECT * FROM users WHERE email=?').get(email);
  if (!user) return res.json({ message: '如果邮箱存在，重置邮件将会发送' });
  const raw = token(24);
  db.prepare('INSERT INTO password_resets (user_id,token_hash,expires_at,created_at) VALUES (?,?,?,?)').run(user.id, sha256(raw), addDays(1 / 48), now());
  const resetUrl = `${appUrl}/?reset=${raw}`;
  try {
    const sent = await sendMail({ to: email, subject: '课伴AI重置密码', text: `请打开此链接重置密码（30分钟内有效）：${resetUrl}` });
    const payload = { message: '如果邮箱存在，重置邮件将会发送', emailSent: sent };
    if (!sent && process.env.NODE_ENV !== 'production' && process.env.ALLOW_DEV_EMAIL_CODE !== 'false') payload.devResetToken = raw;
    res.json(payload);
  } catch (error) { res.status(503).json({ error: error.message }); }
});

app.post('/api/auth/reset-password', (req, res) => {
  const raw = String(req.body.token || '');
  const password = String(req.body.password || '');
  if (password.length < 8) return res.status(400).json({ error: '密码至少8位' });
  const record = db.prepare('SELECT * FROM password_resets WHERE token_hash=? AND consumed_at IS NULL AND expires_at>?').get(sha256(raw), now());
  if (!record) return res.status(400).json({ error: '重置链接无效或已过期' });
  db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(bcrypt.hashSync(password, 12), record.user_id);
  db.prepare('UPDATE password_resets SET consumed_at=? WHERE id=?').run(now(), record.id);
  db.prepare('DELETE FROM sessions WHERE user_id=?').run(record.user_id);
  res.json({ message: '密码已重置，请重新登录' });
});

app.post('/api/auth/change-password', requireAuth, (req, res) => {
  const oldPassword = String(req.body.oldPassword || '');
  const newPassword = String(req.body.newPassword || '');
  if (!bcrypt.compareSync(oldPassword, req.user.password_hash)) return res.status(400).json({ error: '旧密码错误' });
  if (newPassword.length < 8) return res.status(400).json({ error: '新密码至少8位' });
  db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(bcrypt.hashSync(newPassword, 12), req.user.id);
  res.json({ message: '密码修改成功' });
});

app.get('/api/plans', (_req, res) => res.json({ plans: Object.entries(plans).map(([name, value]) => ({ name, amount: value.amount, displayAmount: value.amount / 100, days: value.days })) }));

app.post('/api/payments/checkout', requireAuth, async (req, res) => {
  const plan = plans[req.body.plan];
  if (!plan) return res.status(400).json({ error: '套餐不存在' });
  const order = db.prepare('INSERT INTO orders (user_id,plan,amount,provider,status,created_at) VALUES (?,?,?,?,?,?)').run(req.user.id, req.body.plan, plan.amount, process.env.STRIPE_SECRET_KEY ? 'stripe' : 'local', 'pending', now());
  if (!process.env.STRIPE_SECRET_KEY) return res.json({ mode: 'local', orderId: order.lastInsertRowid, checkoutUrl: `${appUrl}/api/payments/local/${order.lastInsertRowid}` });
  const params = new URLSearchParams();
  params.set('mode', 'payment');
  params.set('success_url', process.env.STRIPE_SUCCESS_URL || `${appUrl}/?payment=success`);
  params.set('cancel_url', process.env.STRIPE_CANCEL_URL || `${appUrl}/?payment=cancelled`);
  params.set('line_items[0][price_data][currency]', 'cny');
  params.set('line_items[0][price_data][product_data][name]', `课伴AI ${req.body.plan}`);
  params.set('line_items[0][price_data][unit_amount]', String(plan.amount));
  params.set('line_items[0][quantity]', '1');
  params.set('metadata[order_id]', String(order.lastInsertRowid));
  try {
    const stripeResponse = await fetch('https://api.stripe.com/v1/checkout/sessions', { method: 'POST', headers: { Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY}`, 'Content-Type': 'application/x-www-form-urlencoded' }, body: params });
    const session = await stripeResponse.json();
    if (!stripeResponse.ok) throw new Error(session.error?.message || 'Stripe 创建支付失败');
    db.prepare('UPDATE orders SET provider_session_id=? WHERE id=?').run(session.id, order.lastInsertRowid);
    res.json({ mode: 'stripe', orderId: order.lastInsertRowid, checkoutUrl: session.url });
  } catch (error) { db.prepare('UPDATE orders SET status=? WHERE id=?').run('failed', order.lastInsertRowid); res.status(502).json({ error: error.message }); }
});

app.get('/api/payments/local/:id', requireAuth, (req, res) => {
  const order = db.prepare('SELECT * FROM orders WHERE id=? AND user_id=?').get(req.params.id, req.user.id);
  if (!order) return res.status(404).send('订单不存在');
  res.type('html').send(`<!doctype html><meta charset="utf-8"><title>课伴AI本地支付</title><style>body{font-family:system-ui;max-width:520px;margin:12vh auto;padding:24px}button{padding:12px 18px;background:#2168f5;color:#fff;border:0;border-radius:8px;font-size:16px}</style><h1>本地支付测试</h1><p>订单 ${order.id} · ${order.plan} · ¥${(order.amount / 100).toFixed(2)}</p><form method="post" action="/api/payments/local/${order.id}/complete"><button>确认测试支付</button></form>`);
});

app.post('/api/payments/local/:id/complete', requireAuth, (req, res) => {
  const order = db.prepare('SELECT * FROM orders WHERE id=? AND user_id=?').get(req.params.id, req.user.id);
  if (!order) return res.status(404).send('订单不存在');
  if (order.status !== 'paid') grantVip(order);
  res.redirect(303, '/?payment=success');
});

app.post('/api/webhooks/stripe', express.raw({ type: 'application/json' }), (req, res) => {
  if (!process.env.STRIPE_WEBHOOK_SECRET) return res.status(503).send('webhook 未配置');
  const signature = req.headers['stripe-signature'] || '';
  const timestamp = signature.match(/t=(\d+)/)?.[1];
  const received = signature.match(/v1=([a-f0-9]+)/)?.[1];
  const expected = timestamp ? crypto.createHmac('sha256', process.env.STRIPE_WEBHOOK_SECRET).update(`${timestamp}.${req.body.toString()}`).digest('hex') : '';
  if (!received || !expected || !crypto.timingSafeEqual(Buffer.from(received), Buffer.from(expected))) return res.status(400).send('签名错误');
  const event = JSON.parse(req.body.toString());
  if (event.type === 'checkout.session.completed') {
    const orderId = Number(event.data.object.metadata?.order_id);
    const order = db.prepare('SELECT * FROM orders WHERE id=?').get(orderId);
    if (order && order.status !== 'paid') grantVip(order);
  }
  res.json({ received: true });
});

app.get('/api/orders', requireAuth, (req, res) => res.json({ orders: db.prepare('SELECT id,plan,amount,currency,provider,status,paid_at,created_at FROM orders WHERE user_id=? ORDER BY id DESC').all(req.user.id) }));

app.post('/api/support/messages', requireAuth, (req, res) => {
  const content = String(req.body.content || '').trim();
  if (!content || content.length > 2000) return res.status(400).json({ error: '留言不能为空且不能超过2000字' });
  db.prepare('INSERT INTO support_messages (user_id,content,created_at) VALUES (?,?,?)').run(req.user.id, content, now());
  res.status(201).json({ message: '留言已提交，管理员会尽快回复' });
});

app.get('/api/learning/records', requireAuth, (req, res) => res.json({ records: db.prepare('SELECT kind,score,payload,created_at FROM learning_records WHERE user_id=? ORDER BY id DESC LIMIT 50').all(req.user.id) }));
app.post('/api/learning/records', requireAuth, (req, res) => {
  const kind = String(req.body.kind || '').trim();
  const score = Number.isFinite(Number(req.body.score)) ? Number(req.body.score) : null;
  if (!kind) return res.status(400).json({ error: '学习记录类型不能为空' });
  db.prepare('INSERT INTO learning_records (user_id,kind,score,payload,created_at) VALUES (?,?,?,?,?)').run(req.user.id, kind, score, JSON.stringify(req.body.payload || {}), now());
  res.status(201).json({ ok: true });
});

app.get('/api/admin/overview', requireAuth, requireAdmin, (_req, res) => {
  const users = db.prepare('SELECT id,username,email,role,email_verified_at,vip_until,created_at FROM users ORDER BY id DESC').all();
  const orders = db.prepare('SELECT o.*,u.username FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC').all();
  const messages = db.prepare('SELECT m.*,u.username FROM support_messages m JOIN users u ON u.id=m.user_id ORDER BY m.id DESC').all();
  res.json({ users, orders, messages });
});
app.post('/api/admin/messages/:id/reply', requireAuth, requireAdmin, (req, res) => {
  const reply = String(req.body.reply || '').trim();
  if (!reply) return res.status(400).json({ error: '回复不能为空' });
  db.prepare('UPDATE support_messages SET reply=?,replied_at=? WHERE id=?').run(reply, now(), req.params.id);
  res.json({ ok: true });
});

app.use(express.static(path.join(__dirname, 'public')));
app.get('*', (req, res, next) => req.path.startsWith('/api/') ? next() : res.sendFile(path.join(__dirname, 'public', 'index.html')));
app.use((err, _req, res, _next) => { console.error(err); res.status(500).json({ error: '服务器内部错误' }); });
app.listen(port, () => console.log(`课伴AI正式版运行于 ${appUrl}`));
