const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let currentUser = null;
let verifyEmail = '';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

function toast(message) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => node.classList.remove('show'), 2800);
}

function showForm(name) {
  $$('[data-form]').forEach((form) => form.classList.toggle('hidden', form.dataset.form !== name));
  $$('[data-auth-tab]').forEach((tab) => tab.classList.toggle('active', tab.dataset.authTab === name));
}

function showAuth() { $('#authView').classList.remove('hidden'); $('#appView').classList.add('hidden'); }
function showApp() { $('#authView').classList.add('hidden'); $('#appView').classList.remove('hidden'); updateUserBadge(); route(location.hash.slice(1) || 'home'); }
function updateUserBadge() { if (!currentUser) return; $('#userBadge').textContent = `${currentUser.username} · ${currentUser.vipUntil && new Date(currentUser.vipUntil) > new Date() ? 'VIP会员' : '免费版'}`; $('[data-admin-only]').classList.toggle('hidden', currentUser.role !== 'admin'); }
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }
function formatDate(value) { return value ? new Date(value).toLocaleDateString('zh-CN') : '-'; }

async function boot() {
  const resetToken = new URLSearchParams(location.search).get('reset');
  if (resetToken) { showAuth(); showForm('reset'); $('[data-form="reset"] [name="token"]').value = resetToken; return; }
  try { const data = await api('/api/auth/me'); currentUser = data.user; } catch { currentUser = null; }
  currentUser ? showApp() : showAuth();
}

$$('[data-auth-tab]').forEach((tab) => tab.addEventListener('click', () => showForm(tab.dataset.authTab)));
$('[data-action="forgot"]').addEventListener('click', () => showForm('reset-request'));
$('[data-action="back-login"]').addEventListener('click', () => showForm('login'));

$('#loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { currentUser = (await api('/api/auth/login', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) })).user; showApp(); toast('登录成功'); }
  catch (error) { toast(error.message); }
});

$('#registerForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const data = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
    verifyEmail = event.currentTarget.email.value.trim().toLowerCase();
    $('#verifyEmail').textContent = verifyEmail; $('[data-form="verify"] [name="email"]').value = verifyEmail; showForm('verify');
    if (data.devCode) toast(`开发验证码：${data.devCode}`); else toast('验证码已发送，请查收邮箱');
  } catch (error) { toast(error.message); }
});

$('#verifyForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { currentUser = (await api('/api/auth/verify-email', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) })).user; showApp(); toast('邮箱验证成功'); }
  catch (error) { toast(error.message); }
});

$('[data-action="resend"]').addEventListener('click', async () => {
  try { const data = await api('/api/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email: verifyEmail }) }); if (data.devCode) toast(`开发验证码：${data.devCode}`); else toast('验证码已重新发送'); }
  catch (error) { toast(error.message); }
});

$('#resetRequestForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { const data = await api('/api/auth/forgot-password', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) }); if (data.devResetToken) toast(`开发重置令牌：${data.devResetToken}`); else toast('如果邮箱存在，重置邮件将会发送'); }
  catch (error) { toast(error.message); }
});

$('#resetForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await api('/api/auth/reset-password', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) }); history.replaceState({}, '', '/'); showForm('login'); toast('密码已重置'); }
  catch (error) { toast(error.message); }
});

document.addEventListener('click', async (event) => {
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (action === 'logout') { await api('/api/auth/logout', { method: 'POST' }); currentUser = null; showAuth(); showForm('login'); toast('已退出登录'); }
  if (action === 'support') submitSupport();
  if (action === 'start-preview') saveLearning('preview', 72);
  if (action === 'start-review') saveLearning('review', 80);
  if (action === 'buy') startCheckout(event.target.closest('[data-plan]').dataset.plan);
});

window.addEventListener('hashchange', () => currentUser && route(location.hash.slice(1) || 'home'));

function route(name) {
  const pages = { home: homePage, preview: previewPage, review: reviewPage, homework: homeworkPage, membership: membershipPage, admin: adminPage };
  (pages[name] || pages.home)();
  $$('#nav a').forEach((link) => link.classList.toggle('active', link.getAttribute('href') === `#${name}`));
}

function shell(title, subtitle, body) { $('#page').innerHTML = `<div class="page"><div class="page-title"><div class="eyebrow">KEBAN AI</div><h1>${title}</h1><p>${subtitle}</p></div>${body}<div class="section"><small class="muted">正式版数据由服务器保存。教材内容、AI批改和语音能力可在后端继续接入。</small></div></div>`; }

function homePage() {
  shell('', '', `<section class="hero"><div><div class="eyebrow">英语 · 学习助手</div><h1>今天，也给英语学习一个清晰的开始。</h1><p>按课本单元掌握核心词汇、句法与语篇逻辑，完成一次小而确定的进步。</p><span class="badge">${currentUser.vipUntil && new Date(currentUser.vipUntil) > new Date() ? `VIP有效至 ${formatDate(currentUser.vipUntil)}` : '免费版'}</span></div><div class="book"></div></section><div class="section"><div class="section-head"><h2>开始学习</h2><span class="muted">Unit 1 Teenage Life</span></div><div class="grid grid-3"><a class="card feature" href="#preview"><span class="icon">▣</span><h3>课本预习</h3><p>课文、生词和长难句解读。</p></a><a class="card feature" href="#review"><span class="icon">↺</span><h3>课本复习</h3><p>知识点回顾与基础检测。</p></a><a class="card feature" href="#homework"><span class="icon">✎</span><h3>作业中心</h3><p>粘贴作业并获取反馈。</p></a></div></div><div class="section"><div class="section-head"><h2>账户服务</h2></div><div class="grid grid-2"><div class="card"><h3>会员中心</h3><p>月卡、季卡、年卡，支付完成后自动开通权益。</p><a class="primary" href="#membership">查看套餐</a></div><div class="card"><h3>联系客服</h3><p>遇到教材、订单或账号问题，可以直接留言。</p><button class="ghost" data-action="open-support">提交留言</button></div></div></div>`);
  bindSupportButton();
}

function previewPage() { shell('课本预习', '从课文语境开始，先理解，再记忆。', `<div class="grid grid-2"><div class="card"><h3>Getting to know the new school</h3><p class="lesson">A week after the first day of senior high school, Adam is still trying to find his way around the new campus. He joined the football team and discovered that making friends can make a new life feel much easier.</p><div class="callout"><strong>AI长难句解读</strong><br>先抓主干 Adam is trying，再补充时间状语和不定式宾语。</div></div><div class="card"><h3>预习检测</h3><p>完成后会记录学习成绩，并生成短期巩固计划。</p><div class="plan"><strong>建议计划</strong><ul><li>今天15分钟：复习6个易混词并听写。</li><li>明天20分钟：拆解2个长难句。</li><li>第3天10分钟：完成听力小练习。</li></ul></div><button class="primary" data-action="start-preview">完成预习并记录</button></div></div><div class="section"><div class="section-head"><h2>核心词汇</h2></div><div class="grid grid-3">${['challenge','confused','recommend','responsible','schedule','improve'].map((word) => `<div class="card word"><strong>${word}</strong><p>本单元高频词汇与例句</p></div>`).join('')}</div></div>`); }

function reviewPage() { shell('课本复习', '把知识点串起来，再用练习确认掌握。', `<div class="grid grid-2"><div class="card"><h3>Unit 1 知识点回顾</h3><p>词汇：teenager · volunteer · debate</p><p>语法：名词短语与定语从句</p><p>语篇：校园生活类记叙文结构</p></div><div class="card"><h3>基础检测</h3><p>共5题 · 预计5分钟 · 上次正确率80%</p><div class="plan"><strong>本次重点</strong><ul><li>从句边界识别</li><li>confused / confusing 词义辨析</li></ul></div><button class="primary" data-action="start-review">完成检测并记录80分</button></div></div>`); }

function homeworkPage() { shell('作业中心', '粘贴英语作业，快速得到错题反馈。', `<div class="grid grid-2"><div class="card"><h3>录入英语作业</h3><textarea id="homeworkText" placeholder="例如：I am confusing about the schedule..."></textarea><button class="primary" data-action="grade-homework">提交AI批改</button></div><div class="card" id="homeworkResult"><p>提交一段作业后，这里会出现批改结果。</p></div></div>`); $('#page [data-action="grade-homework"]').addEventListener('click', () => { const text = $('#homeworkText').value.trim(); if (!text) return toast('请先粘贴英语作业'); $('#homeworkResult').innerHTML = currentUser.vipUntil && new Date(currentUser.vipUntil) > new Date() ? '<h3>逐题讲解</h3><p>confusing 描述“令人困惑的事物”，描述人的感受应使用 confused。</p><div class="callout">建议改为：I am confused about the schedule.</div>' : '<h3>简略批改</h3><p>第1题需修改，第2题正确。</p><div class="notice">开通会员后解锁逐题完整讲解。</div>'; }); }

function membershipPage() { shell('会员中心', '解锁完整AI讲解与英语学习资源。', `<div class="grid grid-3">${[['月卡',10,'灵活体验'],['季卡',20,'阶段冲刺'],['年卡',60,'性价比最高']].map(([plan, price, note]) => `<div class="card plan-card"><span class="badge ${plan === '年卡' ? '' : 'free'}">${note}</span><h3>${plan}</h3><div class="price"><strong>¥${price}</strong><small> / ${plan.slice(0,1)}</small></div><p>AI作业逐题讲解、四维能力评级、模拟试卷。</p><button class="${plan === '年卡' ? 'primary' : 'ghost'} full" data-action="buy" data-plan="${plan}">立即开通</button></div>`).join('')}</div><div class="section card"><h3>支付说明</h3><p>已配置 Stripe 商户时跳转真实 Checkout；开发环境未配置密钥时，会打开本地测试支付页，不会产生真实扣款。</p></div>`); }

async function startCheckout(plan) {
  try { const data = await api('/api/payments/checkout', { method: 'POST', body: JSON.stringify({ plan }) }); window.location.href = data.checkoutUrl; }
  catch (error) { toast(error.message); }
}

async function saveLearning(kind, score) { try { await api('/api/learning/records', { method: 'POST', body: JSON.stringify({ kind, score, payload: { unit: 'Unit 1 Teenage Life' } }) }); toast(`${kind === 'preview' ? '预习' : '复习'}已记录`); } catch (error) { toast(error.message); } }

function bindSupportButton() { $('[data-action="open-support"]')?.addEventListener('click', () => { $('#page').insertAdjacentHTML('beforeend', '<div class="card" id="supportBox"><h3>联系客服</h3><textarea id="supportText" placeholder="请输入留言内容"></textarea><button class="primary" data-action="support">提交留言</button></div>'); }); }
async function submitSupport() { const content = $('#supportText')?.value.trim(); if (!content) return toast('请输入留言内容'); try { await api('/api/support/messages', { method: 'POST', body: JSON.stringify({ content }) }); toast('留言已提交'); $('#supportBox').remove(); } catch (error) { toast(error.message); } }

async function adminPage() {
  if (currentUser.role !== 'admin') return shell('无权限', '管理员账号才可以访问此页面。', '<div class="card"><p>请使用管理员账号登录。</p></div>');
  let data; try { data = await api('/api/admin/overview'); } catch (error) { return shell('管理后台', error.message, ''); }
  shell('管理后台', '查看用户、订单和客服留言。', `<div class="admin-tabs"><button class="active" data-admin-tab="users">用户管理</button><button data-admin-tab="orders">消费记录</button><button data-admin-tab="messages">客服留言</button></div><div id="adminContent"></div>`);
  const draw = (tab = 'users') => { $$('.admin-tabs button').forEach((button) => button.classList.toggle('active', button.dataset.adminTab === tab)); const box = $('#adminContent'); if (tab === 'users') box.innerHTML = `<div class="card table-wrap"><table class="table"><thead><tr><th>用户名</th><th>邮箱</th><th>角色</th><th>验证</th><th>VIP到期</th></tr></thead><tbody>${data.users.map((user) => `<tr><td>${escapeHtml(user.username)}</td><td>${escapeHtml(user.email)}</td><td>${user.role}</td><td>${user.email_verified_at ? '已验证' : '未验证'}</td><td>${formatDate(user.vip_until)}</td></tr>`).join('')}</tbody></table></div>`; if (tab === 'orders') box.innerHTML = `<div class="card table-wrap"><table class="table"><thead><tr><th>用户</th><th>套餐</th><th>金额</th><th>状态</th><th>时间</th></tr></thead><tbody>${data.orders.map((order) => `<tr><td>${escapeHtml(order.username)}</td><td>${order.plan}</td><td>¥${(order.amount / 100).toFixed(2)}</td><td>${order.status}</td><td>${formatDate(order.created_at)}</td></tr>`).join('') || '<tr><td colspan="5">暂无订单</td></tr>'}</tbody></table></div>`; if (tab === 'messages') box.innerHTML = `<div class="card table-wrap"><table class="table"><thead><tr><th>用户</th><th>留言</th><th>状态</th><th>操作</th></tr></thead><tbody>${data.messages.map((message) => `<tr><td>${escapeHtml(message.username)}</td><td>${escapeHtml(message.content)}</td><td>${message.replied_at ? '已回复' : '待回复'}</td><td>${message.replied_at ? '' : `<button class="ghost reply" data-id="${message.id}">回复</button>`}</td></tr>`).join('') || '<tr><td colspan="4">暂无留言</td></tr>'}</tbody></table></div>`; };
  $$('.admin-tabs button').forEach((button) => button.addEventListener('click', () => draw(button.dataset.adminTab))); draw();
  $('#adminContent').addEventListener('click', async (event) => { const button = event.target.closest('.reply'); if (!button) return; const reply = window.prompt('请输入回复内容'); if (!reply) return; await api(`/api/admin/messages/${button.dataset.id}/reply`, { method: 'POST', body: JSON.stringify({ reply }) }); toast('回复已保存'); data = await api('/api/admin/overview'); draw('messages'); });
}

boot();
