<script>
import { loadAuth, userStore, refreshUser } from './store/user'

export default {
  onLaunch() {
    loadAuth()
    // 未登录直接进登录页。放在 onLaunch 而不是各页面的 onShow 里，
    // 是为了避免每个 tab 页都写一遍跳转判断。
    if (!userStore.token) {
      uni.reLaunch({ url: '/pages/login/login' })
      return
    }
    // 本地用户信息可能是旧的（会员到期、后台改角色），静默拉一次最新值。
    // 失败不打断启动——多半是断网或 token 过期，request.js 会自行处理 401。
    refreshUser().catch(() => {})
  },

  onShow() {
    // 从后台切回来时刷新会员状态，避免刚开通完还显示「免费版」
    if (userStore.token) refreshUser().catch(() => {})
  },
}
</script>

<style>
/* ------------------------------------------------------------------ */
/* 全局样式：uni-app 会把 App.vue 的样式注入到所有页面                  */
/* ------------------------------------------------------------------ */

page {
  background-color: #f5f7fb;
  color: #1f2937;
  font-size: 28rpx;
  line-height: 1.6;
}

.page {
  padding: 24rpx;
  padding-bottom: 48rpx;
}

/* 卡片 */
.card {
  background: #ffffff;
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 24rpx;
  box-shadow: 0 2rpx 12rpx rgba(31, 41, 55, 0.04);
}

.card__title {
  font-size: 32rpx;
  font-weight: 600;
  margin-bottom: 16rpx;
}

.card__caption {
  font-size: 24rpx;
  color: #9ca3af;
}

/* 通用文字 */
.title {
  font-size: 36rpx;
  font-weight: 700;
  margin-bottom: 8rpx;
}

.subtitle {
  font-size: 32rpx;
  font-weight: 600;
  margin: 24rpx 0 16rpx;
}

.caption {
  font-size: 24rpx;
  color: #9ca3af;
}

.muted {
  color: #6b7280;
}

.text-success { color: #1f9d55; }
.text-warning { color: #d97706; }
.text-danger  { color: #dc2626; }

/* 布局 */
.row {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.row--between {
  justify-content: space-between;
}

.col {
  display: flex;
  flex-direction: column;
}

.flex-1 { flex: 1; }
.mt-16 { margin-top: 16rpx; }
.mt-24 { margin-top: 24rpx; }
.mb-16 { margin-bottom: 16rpx; }

/* 按钮 */
.btn {
  height: 88rpx;
  line-height: 88rpx;
  border-radius: 16rpx;
  font-size: 30rpx;
  text-align: center;
  background: #2a78d6;
  color: #ffffff;
  border: none;
}

.btn::after { border: none; }

.btn--ghost {
  background: #ffffff;
  color: #2a78d6;
  border: 2rpx solid #2a78d6;
}

.btn--plain {
  background: #f1f3f8;
  color: #4b5563;
}

.btn--danger {
  background: #fff1f1;
  color: #dc2626;
}

.btn[disabled] {
  opacity: 0.5;
}

/* 表单 */
.field {
  margin-bottom: 24rpx;
}

.field__label {
  font-size: 26rpx;
  color: #6b7280;
  margin-bottom: 12rpx;
}

.field__input {
  height: 88rpx;
  background: #f7f8fc;
  border-radius: 12rpx;
  padding: 0 24rpx;
  font-size: 28rpx;
}

.field__textarea {
  width: 100%;
  min-height: 240rpx;
  background: #f7f8fc;
  border-radius: 12rpx;
  padding: 20rpx 24rpx;
  font-size: 28rpx;
  box-sizing: border-box;
}

/* 标签 */
.chip {
  display: inline-block;
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
  font-size: 22rpx;
  line-height: 1.6;
}

.chip--success { background: #e7f6ed; color: #1f9d55; }
.chip--warning { background: #fdf3e3; color: #d97706; }
.chip--danger  { background: #fdeaea; color: #dc2626; }
.chip--info    { background: #e8f1fc; color: #2a78d6; }
.chip--vip     { background: #fdf3e3; color: #b7791f; }
.chip--plain   { background: #f1f3f8; color: #6b7280; }

/* 空状态 */
.empty {
  padding: 80rpx 24rpx;
  text-align: center;
  color: #9ca3af;
  font-size: 26rpx;
}

.empty__icon { font-size: 64rpx; display: block; margin-bottom: 16rpx; }

/* 分割线 */
.divider {
  height: 2rpx;
  background: #eef0f5;
  margin: 24rpx 0;
}

/* 加载中 */
.loading {
  padding: 60rpx;
  text-align: center;
  color: #9ca3af;
  font-size: 26rpx;
}

/* 安全区 */
.safe-bottom {
  height: calc(24rpx + constant(safe-area-inset-bottom));
  height: calc(24rpx + env(safe-area-inset-bottom));
}
</style>
