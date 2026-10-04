<template>
  <view class="page">
    <view class="card">
      <view class="field">
        <text class="field__label">用户名（英文名）</text>
        <input v-model="form.username" class="field__input" placeholder="2~20 位英文字母" placeholder-class="ph" />
      </view>

      <view class="field">
        <text class="field__label">中文名</text>
        <input v-model="form.chinese_name" class="field__input" placeholder="真实姓名，如：张三" placeholder-class="ph" />
      </view>

      <view class="field">
        <text class="field__label">邮箱</text>
        <input v-model="form.email" class="field__input" placeholder="用于接收验证码" placeholder-class="ph" />
      </view>

      <view class="field">
        <text class="field__label">验证码</text>
        <view class="code-row">
          <input v-model="form.code" class="field__input code-row__input" placeholder="6 位数字" placeholder-class="ph" />
          <button class="btn btn--ghost code-row__btn" :disabled="counting || sending" @tap="sendCode">
            {{ counting ? `${countdown}s 后重发` : '获取验证码' }}
          </button>
        </view>
      </view>

      <view v-if="devCode" class="dev-code">
        <text>演示环境验证码：{{ devCode }}（生产环境不会显示）</text>
      </view>

      <view class="field">
        <text class="field__label">密码</text>
        <input v-model="form.password" class="field__input" password placeholder="至少 6 位，需含字母和数字" placeholder-class="ph" />
      </view>

      <view class="field">
        <text class="field__label">确认密码</text>
        <input
          v-model="form.confirm_password"
          class="field__input"
          password
          placeholder="再输入一次密码"
          placeholder-class="ph"
        />
      </view>

      <button class="btn mt-16" :disabled="loading" @tap="submit">
        {{ loading ? '注册中…' : '注册并登录' }}
      </button>

      <view class="caption" style="text-align: center; margin-top: 24rpx">
        已有账号？<text class="link" @tap="back">返回登录</text>
      </view>
    </view>
    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 注册页：邮箱验证码 + 账号密码。
 *
 * 验证码规则（60 秒可重发、5 次尝试上限、10 分钟有效）全在后端，
 * 这里只负责倒计时展示——客户端计时只是体验，不构成任何安全边界。
 */
import { onUnmounted, reactive, ref } from 'vue'

import { authApi } from '../../api'
import { setAuth } from '../../store/user'

const form = reactive({
  username: '',
  chinese_name: '',
  email: '',
  code: '',
  password: '',
  confirm_password: '',
})

const loading = ref(false)
const sending = ref(false)
const countdown = ref(0)
const devCode = ref('')
let timer = null

const counting = ref(false)

async function sendCode() {
  const email = form.email.trim()
  if (!email) {
    uni.showToast({ title: '请先填写邮箱', icon: 'none' })
    return
  }
  sending.value = true
  try {
    const res = await authApi.sendCode(email)
    devCode.value = res.dev_code || ''
    uni.showToast({ title: res.message || '验证码已发送', icon: 'none' })
    startCountdown()
  } catch (err) {
    uni.showToast({ title: err.message || '发送失败', icon: 'none' })
  } finally {
    sending.value = false
  }
}

function startCountdown() {
  countdown.value = 60
  counting.value = true
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) stopCountdown()
  }, 1000)
}

function stopCountdown() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  counting.value = false
}

onUnmounted(stopCountdown)

async function submit() {
  if (
    !form.username.trim() ||
    !form.chinese_name.trim() ||
    !form.email.trim() ||
    !form.code.trim() ||
    !form.password
  ) {
    uni.showToast({ title: '请把信息填写完整', icon: 'none' })
    return
  }
  if (form.password !== form.confirm_password) {
    uni.showToast({ title: '两次输入的密码不一致', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await authApi.register({
      username: form.username.trim(),
      chinese_name: form.chinese_name.trim(),
      email: form.email.trim(),
      password: form.password,
      confirm_password: form.confirm_password,
      code: form.code.trim(),
    })
    setAuth(res.token, res.user)
    uni.showToast({ title: '注册成功', icon: 'success' })
    setTimeout(() => uni.switchTab({ url: '/pages/home/home' }), 500)
  } catch (err) {
    uni.showToast({ title: err.message || '注册失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function back() {
  uni.navigateBack()
}
</script>

<style scoped>
.code-row {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.code-row__input {
  flex: 1;
}

.code-row__btn {
  width: 220rpx;
  height: 88rpx;
  line-height: 88rpx;
  font-size: 26rpx;
  margin-left: 16rpx;
  padding: 0;
}

.dev-code {
  background: #fdf3e3;
  color: #b7791f;
  font-size: 24rpx;
  padding: 16rpx 20rpx;
  border-radius: 12rpx;
  margin-bottom: 24rpx;
}

.link {
  color: #2a78d6;
}

.ph {
  color: #c0c4cc;
}
</style>
