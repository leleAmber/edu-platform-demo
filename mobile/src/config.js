/**
 * 全局配置。
 *
 * ★ 上线前必须改 BASE_URL ★
 *
 * 微信小程序只允许请求已在「微信公众平台 → 开发管理 → 开发设置 → 服务器域名」
 * 里配置过的 HTTPS 域名，且该域名必须已完成 ICP 备案。
 *
 * 本地联调有两条路：
 *   1. 微信开发者工具 → 详情 → 本地设置 → 勾选「不校验合法域名…」，
 *      然后把 BASE_URL 指到 http://127.0.0.1:8000（本机后端）。
 *   2. 真机预览时手机访问不到 127.0.0.1，需要把 BASE_URL 换成电脑在局域网的 IP，
 *      例如 http://192.168.1.10:8000，并保证后端以 --host 0.0.0.0 启动。
 */

// 生产环境示例：'https://api.your-domain.com'
//
// 想临时换地址又不想改这个文件（例如真机联调要用局域网 IP），
// 就在命令行上带环境变量启动，Vite 会读进 import.meta.env：
//   VITE_API_BASE=http://192.168.1.110:8000 npm run dev:h5 -- --host 0.0.0.0
export const BASE_URL = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

// 请求超时（毫秒）。批改类接口走异步任务，本身很快就返回 job_id，
// 所以这里不需要设很大。
export const TIMEOUT = 20000

// 异步任务轮询间隔（毫秒），与后端 /jobs 返回的 poll_interval 保持一致即可
export const POLL_INTERVAL = 2000

// 轮询上限：150 秒（100 次 × 1.5 秒），与后端的大模型总预算对齐
export const POLL_MAX_TRIES = 100

// 存储 token 的 key
export const TOKEN_KEY = 'keban_token'
export const USER_KEY = 'keban_user'
