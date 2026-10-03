# 课伴AI · 移动端（微信小程序）

用 uni-app（Vue 3 + Vite）开发的微信小程序，一套代码同时可出 H5 / App。
后端是 `../api`（FastAPI），业务逻辑复用 `../core`，
三个模块共用同一个 MySQL，同处一个仓库。网页版（仓库根）继续独立运行，互不影响。

## 快速开始

```bash
npm install

# 微信小程序（主要目标）
npm run dev:mp-weixin       # 产物在 dist/dev/mp-weixin，用微信开发者工具导入
npm run build:mp-weixin     # 产物在 dist/build/mp-weixin，用于提审

# H5（调试用）
npm run dev:h5
npm run build:h5
```

后端要先跑起来（默认 `127.0.0.1:8000`）：

```bash
cd ../api && python run.py
```

## 本地调试

**H5（最快的一圈，零安装）**

```bash
cd ../api && python run.py     # 后端 127.0.0.1:8000
npm run dev:h5                 # 在 mobile/ 目录下
# 浏览器打开 http://localhost:5173  （见下方「只能写 localhost」）
```

用 `student / 123456`（VIP）或 `admin / 123456` 登录，F12 切设备模拟。

**真机 / 局域网**

手机访问不到 `127.0.0.1`，两样都要放开：

```bash
# 1) 后端监听所有网卡
cd api && python run.py --host 0.0.0.0
# 2) 前端也 --host，并把 API 地址指到电脑的局域网 IP
cd mobile
VITE_API_BASE=http://192.168.1.110:8000 npm run dev:h5 -- --host 0.0.0.0
# 手机浏览器打开 http://192.168.1.110:5173
```

跨机器访问还要把 `http://192.168.1.110:5173` 加进后端 CORS，否则响应被浏览器拦掉：

```bash
API_CORS_ORIGINS=http://localhost:5173,http://192.168.1.110:5173 \
  python run.py --host 0.0.0.0
```

**微信开发者工具（真正的目标端）**

```bash
npm run dev:mp-weixin      # 产物在 dist/dev/mp-weixin
```

开发者工具里「导入项目」指向 `dist/dev/mp-weixin`，然后
**详情 → 本地设置 → 勾选「不校验合法域名、web-view(业务域名)、TLS 版本以及 HTTPS 证书」**，
否则 `http://127.0.0.1:8000` 会被小程序运行时拦掉。

## 关于 BASE_URL

[src/config.js](src/config.js) 默认 `http://127.0.0.1:8000`，可用 `VITE_API_BASE`
环境变量临时覆盖（上面真机那条就是），不必去改文件。

- **上线**：必须是**已备案的 HTTPS 域名**，并在微信公众平台 → 开发管理 → 开发设置 →
  服务器域名里配置 `request` 合法域名。

**只能写 `localhost`，不能写 `127.0.0.1`。** 这是 uni-app 的 H5 dev server 只绑 IPv6
（`[::1]:5173`）导致的：`localhost:5173` 通，`127.0.0.1:5173` 连不上。后端 CORS 默认
同时放行了这两个源，所以直接用 `localhost` 即可，不用改配置。

## 目录

```
src/
  config.js             全局配置（BASE_URL 等）
  pages.json            路由与 tabBar
  manifest.json         各端打包配置（appid 待填）
  App.vue               启动逻辑 + 全局样式
  api/
    request.js          uni.request 封装：带 token、错误归一化、401 跳登录
    index.js            接口清单 + pollJob（异步任务轮询）
  store/
    user.js             登录态（reactive，未引 pinia）
    catalog.js          当前教材 / 当前单元（全 App 上下文）
  utils/
    format.js           展示层格式化
    canvas.js           canvas 绘制公共逻辑
  components/           book-picker / quiz-panel / plan-card / unit-study /
                        radar-chart / bar-chart / job-progress / collapse-item …
  pages/                login·register·home·preview·review·homework·
                        exam·membership·diagnosis·messages·mine
scripts/
  smoke-h5.mjs          用无头 Chrome 跑一遍 H5 的冒烟测试（见文件头注释）
```

## 两个关键设计

**1. 批改类接口一律异步。**
作业识别、作业批改、模拟卷阅卷都是「提交拿 `job_id` → 轮询 `/jobs/{id}`」。
原因有两层：微信云托管 `callContainer` 单次调用硬限 15 秒，同步返回必然超时；
手机端干等 30 秒白屏，体验也差。轮询入口统一走 `api/index.js` 的 `pollJob()`。

**2. 答案不下发客户端。**
题目在服务端就已剥离 `answer` / `explain`，批改时服务端回自己的会话缓存取带答案的原卷。
免费用户的逐题解析同样在服务端剥掉（`locked: true`），客户端藏是藏不住的。

## 已知噪音

H5 下控制台会出现 2~4 条
`TypeError: Cannot destructure property 'firstElementChild' of 'e.value' as it is null.`

出自 uni-app 自带的 H5 运行时（`ResizeSensor` 在组件卸载后仍收到 resize 回调），
与本项目代码无关，**小程序产物里不包含这段代码**，不影响功能。

## 待办（上线前）

- [ ] `src/manifest.json` 填 `mp-weixin.appid`（在微信公众平台注册小程序后获得）
- [ ] `src/config.js` 的 `BASE_URL` 换成备案后的 HTTPS 域名
- [ ] 微信公众平台配置 request 合法域名
- [ ] `WX_APPID` / `WX_SECRET` 配到后端，微信一键登录才会生效（否则登录页会提示未配置）
- [ ] tabBar 目前只有文字没有图标；如需图标，在 `pages.json` 的 `tabBar.list` 里补
      `iconPath` / `selectedIconPath`（图片放 `src/static/`）
