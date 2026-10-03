/**
 * 用 Chrome DevTools Protocol 驱动真实浏览器跑一遍 H5 版。
 *
 * 目的不是替代人工验收，而是抓「编译通过、一跑就白屏」这类运行时错误：
 * 未定义的变量、写错的组件名、模板里访问了 undefined 的字段。
 * 小程序端的运行时行为仍需用微信开发者工具人工确认——那套运行时这里驱动不了。
 *
 * 跑之前三件事要就绪：
 *   1. 后端：cd api && python run.py（默认 127.0.0.1:8000）
 *   2. H5 产物：npm run build:h5，然后
 *      cd dist/build/h5 && python3 -m http.server 5173
 *      （端口必须是 5173：后端 CORS 默认只放行 5173 / 8080）
 *   3. 无头 Chrome：
 *      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
 *        --headless=new --disable-gpu --remote-debugging-port=9222 \
 *        --user-data-dir=/tmp/chrome-smoke-profile about:blank &
 *
 * 然后 npm run smoke:h5
 *
 * 已知噪音：H5 下会看到 2~4 条
 *   TypeError: Cannot destructure property 'firstElementChild' of 'e.value' as it is null.
 * 出自 uni-app 自带的 H5 运行时（ResizeSensor 在组件卸载后仍收到 resize 回调），
 * 与本项目代码无关，小程序产物里也没有这段代码，不影响功能。
 */

const CDP_PORT = 9222
const APP = 'http://127.0.0.1:5173'
const USER = 'student'
const PASS = '123456'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function target() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()
      const page = list.find((t) => t.type === 'page')
      if (page) return page
    } catch (e) {
      /* chrome 还没起来 */
    }
    await sleep(250)
  }
  throw new Error('连不上 Chrome 调试端口')
}

class Cdp {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.consoleErrors = []
    this.exceptions = []
    this.requests = []
    ws.addEventListener('message', (event) => {
      const msg = JSON.parse(event.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
        return
      }
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
        const text = msg.params.args.map((a) => a.value ?? a.description ?? '').join(' ')
        const stack = (msg.params.stackTrace?.callFrames || [])
          .map((f) => `${f.functionName || '<anon>'}@${(f.url || '').split('/').pop()}:${f.lineNumber}`)
          .join('  <-  ')
        this.consoleErrors.push(text + (stack ? `\n      ${stack}` : ''))
      }
      if (msg.method === 'Runtime.exceptionThrown') {
        const d = msg.params.exceptionDetails
        const stack = (d.stackTrace?.callFrames || [])
          .map((f) => `${f.functionName || '<anon>'}@${(f.url || '').split('/').pop()}:${f.lineNumber}`)
          .join('  <-  ')
        this.exceptions.push((d.exception?.description || d.text) + (stack ? `\n      ${stack}` : ''))
      }
      if (msg.method === 'Network.responseReceived') {
        this.requests.push({ url: msg.params.response.url, status: msg.params.response.status })
      }
    })
  }

  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error(`CDP 超时: ${method}`))
        }
      }, 30000)
    })
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    })
    if (res.exceptionDetails) {
      throw new Error(res.exceptionDetails.exception?.description || res.exceptionDetails.text)
    }
    return res.result.value
  }
}

const results = []
function check(label, ok, detail = '') {
  results.push({ label, ok, detail })
  console.log(`${ok ? 'OK  ' : 'FAIL'}  ${label}${detail ? `  -> ${detail}` : ''}`)
}

const page = await target()
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve)
  ws.addEventListener('error', reject)
})
const cdp = new Cdp(ws)

await cdp.send('Runtime.enable')
await cdp.send('Page.enable')
await cdp.send('Network.enable')

// --------------------------------------------------------------------- //
// 1. 冷启动：未登录应落在登录页
// --------------------------------------------------------------------- //
// 上一轮跑完会留下登录态。在「新文档创建前」清空存储，确保测的是真正的冷启动。
// 不能先加载再清空——那等于在应用运行时抽掉它的状态，会造出真实场景里不存在的报错。
await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
  source: `try { localStorage.clear(); sessionStorage.clear() } catch (e) {}`,
})
await cdp.send('Page.navigate', { url: APP })
await sleep(3500)

check(
  '冷启动落在登录页',
  (await cdp.eval(`!!document.querySelector('.auth__name')`)) === true,
  await cdp.eval(`location.hash`)
)
check(
  '登录页渲染出品牌名',
  (await cdp.eval(`(document.querySelector('.auth__name')||{}).textContent || ''`)) === '课伴AI'
)

// --------------------------------------------------------------------- //
// 2. 通过真实表单登录
// --------------------------------------------------------------------- //
const inputs = await cdp.eval(`Array.from(document.querySelectorAll('input')).length`)
check('登录表单有 2 个输入框', inputs === 2, `实际 ${inputs}`)

await cdp.eval(`(() => {
  const els = document.querySelectorAll('input')
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  setter.call(els[0], ${JSON.stringify(USER)})
  els[0].dispatchEvent(new Event('input', { bubbles: true }))
  setter.call(els[1], ${JSON.stringify(PASS)})
  els[1].dispatchEvent(new Event('input', { bubbles: true }))
})()`)
await sleep(300)

await cdp.eval(`(() => {
  const btn = Array.from(document.querySelectorAll('uni-button, button')).find((b) => b.textContent.includes('登录') && !b.textContent.includes('微信'))
  btn && btn.click()
})()`)
await sleep(3000)

check(
  '登录后进入首页',
  // uni-app H5 把第一个 tab 页挂在根路由上，所以首页可能是 #/ 而不是 #/pages/home/home
  ['#/', '#/pages/home/home'].includes(await cdp.eval(`location.hash`)),
  await cdp.eval(`location.hash`)
)
check(
  '首页显示欢迎语',
  (await cdp.eval(`(document.querySelector('.hero__hello')||{}).textContent || ''`)).includes('欢迎回来'),
  await cdp.eval(`(document.querySelector('.hero__hello')||{}).textContent || ''`)
)
check(
  '首页教材选择器已加载',
  (await cdp.eval(`document.querySelectorAll('.picker__value').length`)) === 2,
  await cdp.eval(`Array.from(document.querySelectorAll('.picker__value')).map(e=>e.textContent).join(' | ')`)
)

// --------------------------------------------------------------------- //
// 3. 逐页走一遍
// --------------------------------------------------------------------- //
const pages = [
  ['/pages/preview/preview', '.segments__item', '预习页分段控件'],
  ['/pages/review/review', '.segments__item', '复习页分段控件'],
  ['/pages/homework/homework', '.thumbs__add', '作业页上传入口'],
  ['/pages/exam/exam', '.card', '模拟试卷页'],
  ['/pages/membership/membership', '.plan__amount', '会员页套餐价格'],
  ['/pages/diagnosis/diagnosis', 'canvas', '学情诊断雷达图 canvas'],
  ['/pages/messages/messages', '.field__textarea', '留言页输入框'],
  ['/pages/mine/mine', '.profile__name', '我的页账号卡'],
]

for (const [path, selector, label] of pages) {
  const before = cdp.exceptions.length + cdp.consoleErrors.length
  await cdp.eval(`location.hash = '#${path}'`)
  await sleep(2600)
  const found = await cdp.eval(`document.querySelectorAll(${JSON.stringify(selector)}).length`)
  const errs = cdp.exceptions.length + cdp.consoleErrors.length - before
  check(`${label}（${path}）`, found > 0 && errs === 0, `命中 ${found} 个元素，新增错误 ${errs}`)
}

// 预习页点开「基础练习」，确认题目渲染出来了
await cdp.eval(`location.hash = '#/pages/preview/preview'`)
await sleep(2600)
await cdp.eval(`(() => {
  const tab = Array.from(document.querySelectorAll('.segments__item')).find((e) => e.textContent.includes('基础练习'))
  tab && tab.click()
})()`)
await sleep(1200)
check(
  '预习页基础练习渲染出题目与选项',
  (await cdp.eval(`document.querySelectorAll('.quiz').length`)) > 0 &&
    (await cdp.eval(`document.querySelectorAll('.quiz__option').length`)) > 0,
  `题目 ${await cdp.eval(`document.querySelectorAll('.quiz').length`)} 道，选项 ${await cdp.eval(`document.querySelectorAll('.quiz__option').length`)} 个`
)

// 学情诊断：回到诊断页，确认 canvas 真的拿到了尺寸（画布尺寸为 0 就等于白图）
await cdp.eval(`location.hash = '#/pages/diagnosis/diagnosis'`)
await sleep(3000)
const canvasInfo = await cdp.eval(`(() => {
  const c = document.querySelector('canvas')
  if (!c) return null
  return { w: c.width, h: c.height }
})()`)
check('雷达图 canvas 有实际尺寸', !!canvasInfo && canvasInfo.w > 0 && canvasInfo.h > 0, JSON.stringify(canvasInfo))

// --------------------------------------------------------------------- //
// 4. 汇总
// --------------------------------------------------------------------- //
const failed = results.filter((r) => !r.ok)
console.log('\n──────── 汇总 ────────')
console.log(`通过 ${results.length - failed.length} / ${results.length}`)

if (cdp.exceptions.length) {
  console.log('\n未捕获异常：')
  cdp.exceptions.forEach((e) => console.log('  !', String(e).split('\n')[0]))
}
if (cdp.consoleErrors.length) {
  console.log('\nconsole.error：')
  cdp.consoleErrors.forEach((e) => console.log('  !', String(e).split('\n')[0]))
}
const bad = cdp.requests.filter((r) => r.status >= 400)
if (bad.length) {
  console.log('\n失败请求：')
  bad.forEach((r) => console.log('  !', r.status, r.url))
}

ws.close()
process.exit(failed.length ? 1 : 0)
