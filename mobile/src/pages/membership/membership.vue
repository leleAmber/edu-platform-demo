<template>
  <view class="page">
    <view class="caption">开通会员即可解锁模拟试卷、学情诊断与作业逐句批改等全部学习能力。</view>

    <!-- 当前状态 -->
    <view class="card mt-16">
      <view class="row row--between">
        <view class="col flex-1">
          <text class="card__title" style="margin-bottom: 8rpx">当前账号：{{ userStore.user?.username }}</text>
          <text v-if="isVip" class="muted">会员状态：已开通（{{ userStore.user?.vip_plan || '会员' }}）</text>
          <text v-else class="muted">会员状态：暂未开通</text>
          <text class="caption" style="margin-top: 8rpx">
            {{ isVip ? `到期时间：${userStore.user?.vip_until_text}　｜　续费可顺延剩余天数` : '开通后即可使用模拟试卷、学情诊断等 VIP 专属功能。' }}
          </text>
        </view>
        <text class="chip" :class="isVip ? 'chip--vip' : 'chip--plain'">
          {{ isVip ? '👑 VIP 会员' : '免费版' }}
        </text>
      </view>
    </view>

    <!-- 套餐 -->
    <view class="section-title">选择套餐</view>
    <view v-if="loading" class="loading">正在加载套餐…</view>
    <view v-else class="card" v-for="plan in plans" :key="plan.name">
      <view class="row row--between">
        <text class="plan__name">{{ plan.name }}</text>
        <text class="chip" :class="plan.recommended ? 'chip--vip' : 'chip--plain'">
          {{ plan.recommended ? '推荐' : '可选' }}
        </text>
      </view>
      <view class="plan__price">
        <text class="plan__symbol">¥</text>
        <text class="plan__amount">{{ plan.price }}</text>
        <text class="plan__days">/ {{ plan.days }} 天</text>
      </view>
      <text v-for="(benefit, index) in plan.benefits" :key="index" class="plan__benefit">· {{ benefit }}</text>
      <button
        class="btn mt-16"
        :class="plan.recommended ? '' : 'btn--ghost'"
        :disabled="paying === plan.name"
        @tap="confirmBuy(plan)"
      >
        {{ paying === plan.name ? '支付中…' : '立即开通' }}
      </button>
    </view>

    <!-- 权益对比 -->
    <view class="section-title">权益对比</view>
    <view class="card">
      <view class="matrix__head">
        <text class="matrix__feature">功能权益</text>
        <text class="matrix__cell">免费版</text>
        <text class="matrix__cell">VIP</text>
      </view>
      <view v-for="item in featureMatrix" :key="item.feature" class="matrix__row">
        <text class="matrix__feature">{{ item.feature }}</text>
        <text class="matrix__cell" :class="item.free ? 'text-success' : 'muted'">{{ item.free ? '✅' : '—' }}</text>
        <text class="matrix__cell" :class="item.vip ? 'text-success' : 'muted'">{{ item.vip ? '✅' : '—' }}</text>
      </view>
    </view>

    <view class="caption" style="text-align: center; margin-top: 24rpx">
      演示环境为模拟支付，不会产生真实扣款，也不会跳转任何支付页面。
    </view>

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 会员中心：套餐展示 + 模拟支付。
 *
 * 支付是**模拟**的：后端只算到期时间、写订单，没有任何真实扣款。
 * 所以这里没有拉起 wx.requestPayment 的逻辑，直接调 /membership/purchase。
 * 接入真实支付时，改动点是这里 + 后端 process_payment，接口形状不用变。
 */
import { onShow } from '@dcloudio/uni-app'
import { ref } from 'vue'

import { membershipApi } from '../../api'
import { isVip, refreshUser, userStore } from '../../store/user'

const plans = ref([])
const featureMatrix = ref([])
const loading = ref(false)
const paying = ref('')

async function load() {
  if (!userStore.token) return
  loading.value = true
  try {
    const res = await membershipApi.plans()
    plans.value = (res && res.plans) || []
    featureMatrix.value = (res && res.feature_matrix) || []
  } catch (err) {
    uni.showToast({ title: err.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onShow(load)

function confirmBuy(plan) {
  uni.showModal({
    title: '确认订单',
    content: `套餐：${plan.name}\n支付金额：¥${plan.price}\n会员有效期：${plan.days} 天\n\n演示环境为模拟支付，不会产生真实扣款。`,
    confirmText: '确认支付',
    success: (res) => {
      if (res.confirm) buy(plan.name)
    },
  })
}

async function buy(planName) {
  paying.value = planName
  try {
    const res = await membershipApi.purchase(planName)
    if (res && res.user) {
      userStore.user = res.user
    } else {
      await refreshUser()
    }
    uni.showToast({ title: res.message || '开通成功', icon: 'success' })
  } catch (err) {
    uni.showToast({ title: err.message || '开通失败', icon: 'none' })
  } finally {
    paying.value = ''
  }
}
</script>

<style scoped>
.section-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #1f2937;
  margin: 32rpx 0 16rpx;
}

.plan__name {
  font-size: 34rpx;
  font-weight: 700;
  color: #1f2937;
}

.plan__price {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  margin: 16rpx 0;
}

.plan__symbol {
  font-size: 28rpx;
  color: #b7791f;
}

.plan__amount {
  font-size: 56rpx;
  font-weight: 700;
  color: #b7791f;
  line-height: 1.1;
}

.plan__days {
  font-size: 24rpx;
  color: #9ca3af;
  margin-left: 12rpx;
}

.plan__benefit {
  display: block;
  font-size: 25rpx;
  color: #4b5563;
  line-height: 1.8;
}

.matrix__head,
.matrix__row {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.matrix__head {
  border-bottom: 2rpx solid #e5e8ef;
}

.matrix__row:last-child {
  border-bottom: none;
}

.matrix__feature {
  flex: 1;
  font-size: 25rpx;
  color: #4b5563;
  padding-right: 12rpx;
}

.matrix__cell {
  width: 100rpx;
  text-align: center;
  font-size: 24rpx;
  color: #6b7280;
}
</style>
