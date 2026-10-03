<template>
  <view class="page">
    <!-- 账号卡 -->
    <view class="card profile">
      <view class="profile__avatar">{{ avatarText }}</view>
      <view class="profile__info">
        <text class="profile__name">{{ userStore.user?.username || '未登录' }}</text>
        <text class="profile__account">
          {{ userStore.user?.has_wechat ? '微信登录' : userStore.user?.email || '—' }}
        </text>
      </view>
      <text class="chip" :class="isVip ? 'chip--vip' : 'chip--plain'">
        {{ isVip ? '👑 VIP' : '免费版' }}
      </text>
    </view>

    <!-- 会员状态 -->
    <view class="card" @tap="go('/pages/membership/membership')">
      <view class="row row--between">
        <view class="col flex-1">
          <text class="card__title" style="margin-bottom: 6rpx">
            {{ isVip ? `会员有效期至 ${userStore.user?.vip_until_text}` : '暂未开通会员' }}
          </text>
          <text class="caption">
            {{ isVip ? '续费可顺延剩余天数' : '开通可解锁模拟试卷、学情诊断与逐句批改' }}
          </text>
        </view>
        <text class="arrow">›</text>
      </view>
    </view>

    <!-- 功能入口 -->
    <view class="card menu">
      <view class="menu__item" @tap="go('/pages/diagnosis/diagnosis')">
        <text class="menu__icon">📊</text>
        <text class="menu__label">学情诊断</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu__item" @tap="go('/pages/membership/membership')">
        <text class="menu__icon">👑</text>
        <text class="menu__label">会员中心</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu__item" @tap="go('/pages/messages/messages')">
        <text class="menu__icon">💬</text>
        <text class="menu__label">客服留言</text>
        <text class="arrow">›</text>
      </view>
      <view class="menu__item" @tap="showOrders = !showOrders">
        <text class="menu__icon">🧾</text>
        <text class="menu__label">我的消费记录</text>
        <text class="arrow">{{ showOrders ? '⌄' : '›' }}</text>
      </view>
    </view>

    <!-- 消费记录 -->
    <view v-if="showOrders" class="card">
      <view class="card__title">消费记录</view>
      <view v-if="!orders.length" class="empty">
        <text class="empty__icon">🧾</text>
        <text>暂无消费记录。</text>
      </view>
      <template v-else>
        <view class="caption mb-16">共 {{ orders.length }} 笔，累计 ¥{{ totalAmount.toFixed(2) }}</view>
        <view v-for="order in orders" :key="order.order_id" class="order">
          <view class="order__main">
            <text class="order__plan">{{ order.plan_name }}</text>
            <text class="order__meta">{{ order.created_at }}　｜　{{ order.pay_method }}</text>
            <text class="order__meta">有效期至 {{ order.vip_until }}</text>
          </view>
          <view class="order__right">
            <text class="order__amount">¥{{ order.amount }}</text>
            <text class="chip chip--success">{{ order.status }}</text>
          </view>
        </view>
      </template>
    </view>

    <button class="btn btn--danger mt-24" @tap="confirmLogout">退出登录</button>

    <view class="caption" style="text-align: center; margin-top: 24rpx">
      课伴AI · 英语课本智能学习助手
    </view>
    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 我的：账号信息、会员状态、功能入口、消费记录、退出登录。
 *
 * 后台管理（用户/订单/留言）不迁移到移动端——那是运营用的，
 * 继续用网页版 pages/8_admin.py 更顺手。
 */
import { onShow } from '@dcloudio/uni-app'
import { computed, ref } from 'vue'

import { membershipApi } from '../../api'
import { isVip, logout, refreshUser, userStore } from '../../store/user'

const showOrders = ref(false)
const orders = ref([])
const totalAmount = ref(0)

const avatarText = computed(() => {
  const name = (userStore.user && userStore.user.username) || '?'
  return name.slice(0, 1).toUpperCase()
})

async function load() {
  if (!userStore.token) return
  refreshUser().catch(() => {})
  try {
    const res = await membershipApi.orders()
    orders.value = (res && res.orders) || []
    totalAmount.value = (res && res.total_amount) || 0
  } catch (e) {
    orders.value = []
    totalAmount.value = 0
  }
}

onShow(load)

function go(url) {
  uni.navigateTo({ url })
}

function confirmLogout() {
  uni.showModal({
    title: '退出登录',
    content: '确定要退出当前账号吗？',
    confirmText: '退出',
    success: (res) => {
      if (res.confirm) logout()
    },
  })
}
</script>

<style scoped>
.profile {
  display: flex;
  flex-direction: row;
  align-items: center;
}

.profile__avatar {
  width: 100rpx;
  height: 100rpx;
  line-height: 100rpx;
  text-align: center;
  border-radius: 50%;
  background: #2a78d6;
  color: #ffffff;
  font-size: 40rpx;
  font-weight: 600;
  margin-right: 24rpx;
  flex-shrink: 0;
}

.profile__info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.profile__name {
  font-size: 34rpx;
  font-weight: 700;
  color: #1f2937;
}

.profile__account {
  font-size: 23rpx;
  color: #9ca3af;
  margin-top: 6rpx;
}

.menu {
  padding: 0 24rpx;
}

.menu__item {
  display: flex;
  flex-direction: row;
  align-items: center;
  min-height: 100rpx;
  border-bottom: 2rpx solid #f3f4f8;
}

.menu__item:last-child {
  border-bottom: none;
}

.menu__icon {
  font-size: 36rpx;
  margin-right: 20rpx;
}

.menu__label {
  flex: 1;
  font-size: 28rpx;
  color: #1f2937;
}

.arrow {
  font-size: 32rpx;
  color: #c8ccd6;
}

.order {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  padding: 20rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.order:last-child {
  border-bottom: none;
}

.order__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-right: 16rpx;
}

.order__plan {
  font-size: 28rpx;
  color: #1f2937;
}

.order__meta {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 4rpx;
}

.order__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.order__amount {
  font-size: 30rpx;
  font-weight: 700;
  color: #b7791f;
  margin-bottom: 6rpx;
}
</style>
