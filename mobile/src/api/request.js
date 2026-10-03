/**
 * HTTP 请求封装。
 *
 * 统一处理三件事：
 * 1. 自动带 Authorization 头；
 * 2. 把后端的 {"detail": "..."} 错误转成可直接 toast 的文案；
 * 3. 401 时清登录态并跳登录页——token 过期不该让用户在页面上看到原始报错。
 */

import { BASE_URL, TIMEOUT, TOKEN_KEY, USER_KEY } from '../config'

/** 取本地 token。 */
export function getToken() {
  try {
    return uni.getStorageSync(TOKEN_KEY) || ''
  } catch (e) {
    return ''
  }
}

/** 清掉登录态。 */
export function clearAuth() {
  try {
    uni.removeStorageSync(TOKEN_KEY)
    uni.removeStorageSync(USER_KEY)
  } catch (e) {
    /* ignore */
  }
}

// 401 只跳一次登录页：并发请求同时过期时，避免连续 push 多个登录页
let redirecting = false

function handleUnauthorized() {
  clearAuth()
  if (redirecting) return
  redirecting = true
  setTimeout(() => {
    redirecting = false
  }, 1500)
  uni.reLaunch({ url: '/pages/login/login' })
}

/**
 * 发起请求。
 * @returns {Promise<any>} resolve 后端返回的 JSON
 * @throws {Error} 带 message（可直接展示）与 status
 */
export function request(options) {
  const { url, method = 'GET', data, header = {}, timeout = TIMEOUT } = options

  const token = getToken()
  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      header,
      timeout,
      success: (res) => {
        const { statusCode, data: body } = res

        if (statusCode >= 200 && statusCode < 300) {
          resolve(body)
          return
        }

        if (statusCode === 401) {
          handleUnauthorized()
          reject(Object.assign(new Error('登录已过期，请重新登录'), { status: 401 }))
          return
        }

        // FastAPI 的校验错误 detail 是数组，普通错误是字符串
        let message = '请求失败'
        if (body && typeof body.detail === 'string') {
          message = body.detail
        } else if (body && Array.isArray(body.detail) && body.detail.length) {
          message = body.detail[0].msg || message
        } else if (statusCode === 403) {
          message = '该功能为 VIP 专属'
        } else if (statusCode >= 500) {
          message = '服务器开小差了，请稍后重试'
        }

        reject(Object.assign(new Error(message), { status: statusCode }))
      },
      fail: (err) => {
        const hint = (err && err.errMsg) || ''
        let message = '网络连接失败，请检查网络'
        if (hint.indexOf('timeout') >= 0) {
          message = '请求超时，请重试'
        } else if (hint.indexOf('domain') >= 0 || hint.indexOf('合法域名') >= 0) {
          message = '域名未配置：请在开发者工具勾选「不校验合法域名」，或在小程序后台配置服务器域名'
        }
        reject(Object.assign(new Error(message), { status: 0 }))
      },
    })
  })
}

/** 上传文件（作业图片）。uni.uploadFile 与 uni.request 是两套 API，单独包一层。 */
export function upload(url, filePath, formData = {}) {
  const header = {}
  const token = getToken()
  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${BASE_URL}${url}`,
      filePath,
      name: 'files',
      formData,
      header,
      timeout: 60000,
      success: (res) => {
        let body = res.data
        try {
          body = JSON.parse(res.data)
        } catch (e) {
          /* 保持原样 */
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body)
        } else if (res.statusCode === 401) {
          handleUnauthorized()
          reject(Object.assign(new Error('登录已过期，请重新登录'), { status: 401 }))
        } else {
          const message = (body && body.detail) || '图片上传失败'
          reject(Object.assign(new Error(message), { status: res.statusCode }))
        }
      },
      fail: () => reject(Object.assign(new Error('图片上传失败，请重试'), { status: 0 })),
    })
  })
}