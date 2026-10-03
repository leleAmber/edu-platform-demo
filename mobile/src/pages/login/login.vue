<template>
  <view class="page auth">
    <view class="auth__brand">
      <text class="auth__logo">📚</text>
      <text class="auth__name">课伴AI</text>
      <text class="auth__slogan">英语课本智能学习助手</text>
    </view>

    <view class="card">
      <view class="field">
        <text class="field__label">用户名</text>
        <input v-model="username" class="field__input" placeholder="请输入用户名" placeholder-class="ph" />
      </view>
      <view class="field">
        <text class="field__label">密码</text>
        <input
          v-model="password"
          class="field__input"
          password
          placeholder="请输入密码"
          placeholder-class="ph"
          @confirm="submit"
        />
      </view>

      <button class="btn mt-16" :disabled="loading" @tap="submit">
        {{ loading ? '登录中…' : '登录' }}
      </button>

      <view class="auth__links">
        <text class="link" @tap="goRegister">注册新账号</text>
        <text class="link" @tap="forgot">忘记密码？</text>
      </view>
    </view>

    <!-- #ifdef MP-WEIXIN -->
    <button class="btn btn--ghost" :disabled="loading" @tap="wechatLogin">微信一键登录</button>
    <view class="caption" style="text-align: center; margin-top: 16rpx">
      微信登录与账号密码登录是同一套账号体系
    </view>
    <!-- #endif -->

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 登录页。
 *
 * 微信登录与账号密码登录并存：微信首次登录会在后端自动建号（openid 绑定），
 * 之后两种方式进的是同一个用户。后端没配 WX_APPID/WX_SECRET 时会返回 503，
 * 这里直接把提示抛给用户，不做静默降级。
 */
import { ref } from 'vue'

import { authApi } from '../../api'
import { setAuth, userStore } from '../../store/user'

const username = ref('')
const password = ref('')
const loading = ref(false)

// 已有登录态（如从「我的」页退出后又回来）直接进首页，别让用户重登一次
if (userStore.token) {
  uni.switchTab({ url: '/pages/home/home' })
}

async function submit() {
  if (!username.value.trim() || !password.value) {
    uni.showToast({ title: '请填写用户名和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await authApi.login(username.value.trim(), password.value)
    setAuth(res.token, res.user)
    uni.showToast({ title: '登录成功', icon: 'success' })
    setTimeout(() => uni.switchTab({ url: '/pages/home/home' }), 400)
  } catch (err) {
    uni.showToast({ title: err.message || '登录失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goRegister() {
  uni.navigateTo({ url: '/pages/register/register' })
}

function forgot() {
  uni.showModal({
    title: '忘记密码',
    content: '请通过「我的 → 客服留言」联系管理员重置密码。',
    showCancel: false,
  })
}

function wechatLogin() {
  loading.value = true
  uni.login({
    provider: 'weixin',
    success: async (loginRes) => {
      try {
        const res = await authApi.wechatLogin(loginRes.code)
        setAuth(res.token, res.user)
        uni.showToast({ title: '登录成功', icon: 'success' })
        setTimeout(() => uni.switchTab({ url: '/pages/home/home' }), 400)
      } catch (err) {
        uni.showToast({ title: err.message || '微信登录失败', icon: 'none' })
      } finally {
        loading.value = false
      }
    },
    fail: () => {
      loading.value = false
      uni.showToast({ title: '微信登录未完成', icon: 'none' })
    },
  })
}
</script>

<style scoped>
.auth {
  padding-top: 80rpx;
}

.auth__brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 60rpx;
}

.auth__logo {
  font-size: 96rpx;
  line-height: 1.2;
}

.auth__name {
  font-size: 44rpx;
  font-weight: 700;
  color: #1f2937;
  margin-top: 16rpx;
}

.auth__slogan {
  font-size: 26rpx;
  color: #9ca3af;
  margin-top: 8rpx;
}

.auth__links {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  margin-top: 28rpx;
}

.link {
  font-size: 26rpx;
  color: #2a78d6;
}

.ph {
  color: #c0c4cc;
}
</style>
