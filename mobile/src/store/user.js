/**
 * 登录态。
 *
 * 项目没引 pinia —— 全部状态就这一个对象，用 reactive 足够，少一层依赖。
 * 网页版的登录态在 st.session_state，这里在本地存储 + 内存对象，语义一致。
 */

import { computed, reactive } from 'vue'

import { authApi } from '../api'
import { clearAuth as clearStorage, getToken } from '../api/request'
import { TOKEN_KEY, USER_KEY } from '../config'

export const userStore = reactive({
  token: '',
  user: null,
  loaded: false,
})

/** 是否 VIP：直接读后端算好的 is_vip，客户端不重复做日期比较。 */
export const isVip = computed(() => !!(userStore.user && userStore.user.is_vip))

export const isAdmin = computed(() => !!(userStore.user && userStore.user.role === 'admin'))

/** 启动时从本地存储恢复登录态。 */
export function loadAuth() {
  userStore.token = getToken()
  try {
    const cached = uni.getStorageSync(USER_KEY)
    userStore.user = cached ? JSON.parse(cached) : null
  } catch (e) {
    userStore.user = null
  }
  userStore.loaded = true
}

/** 登录/注册成功后写入。 */
export function setAuth(token, user) {
  userStore.token = token || ''
  userStore.user = user || null
  try {
    if (token) uni.setStorageSync(TOKEN_KEY, token)
    if (user) uni.setStorageSync(USER_KEY, JSON.stringify(user))
  } catch (e) {
    /* 存储失败不影响本次会话 */
  }
}

/** 清空登录态（内存 + 本地）。 */
export function resetAuth() {
  userStore.token = ''
  userStore.user = null
  clearStorage()
}

/** 拉取最新的用户信息（会员状态会变，不能只信本地缓存）。 */
export async function refreshUser() {
  const res = await authApi.me()
  if (res && res.user) {
    userStore.user = res.user
    try {
      uni.setStorageSync(USER_KEY, JSON.stringify(res.user))
    } catch (e) {
      /* ignore */
    }
  }
  return userStore.user
}

/** 登出：先通知后端清会话缓存，再清本地。后端失败也照样退出。 */
export async function logout() {
  try {
    await authApi.logout()
  } catch (e) {
    /* 网络不通也要让用户能退出 */
  }
  resetAuth()
  uni.reLaunch({ url: '/pages/login/login' })
}
