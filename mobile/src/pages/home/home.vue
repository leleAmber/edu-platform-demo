<template>
  <view class="page">
    <!-- 欢迎区 -->
    <view class="card hero">
      <view class="hero__main">
        <text class="hero__hello">👋 欢迎回来，{{ userStore.user?.username || '同学' }}</text>
        <text class="hero__desc">选好单元，从预习、复习到作业批改，一步步把课本学透。</text>
      </view>
      <view class="hero__status">
        <text class="chip" :class="isVip ? 'chip--vip' : 'chip--plain'">
          {{ isVip ? '👑 VIP 会员' : '免费版' }}
        </text>
        <text class="hero__until">{{ isVip ? `有效期至 ${userStore.user?.vip_until_text}` : '开通可解锁模拟卷与学情诊断' }}</text>
      </view>
    </view>

    <!-- 教材 / 单元选择 -->
    <book-picker @change="onCatalogChange" />

    <!-- 功能入口 -->
    <view class="section-title">学习功能</view>
    <view class="grid">
      <view v-for="item in features" :key="item.title" class="grid__cell card" @tap="open(item)">
        <text class="grid__icon">{{ item.icon }}</text>
        <view class="grid__head">
          <text class="grid__title">{{ item.title }}</text>
          <text v-if="item.vip" class="chip chip--vip">VIP</text>
        </view>
        <text class="grid__desc">{{ item.desc }}</text>
      </view>
    </view>

    <!-- 今日学习建议 -->
    <view class="section-title">今日学习建议</view>
    <view class="card">
      <view v-for="(tip, index) in tips" :key="index" class="tip">
        <text class="tip__index">{{ index + 1 }}</text>
        <text class="tip__text">{{ tip }}</text>
      </view>
    </view>

    <!-- 最近学习记录 -->
    <view class="section-title">最近学习记录</view>
    <view class="card">
      <view v-if="!records.length" class="empty">
        <text class="empty__icon">📘</text>
        <text>还没有学习记录，先去「课本预习」完成一次练习吧。</text>
      </view>
      <view v-for="(record, index) in records" :key="index" class="record">
        <view class="record__main">
          <text class="record__module">{{ record.module }}</text>
          <text class="record__unit">{{ record.unit || '—' }}</text>
        </view>
        <view class="record__right">
          <text class="record__score" :class="scoreClass(record.score)">{{ record.score }}</text>
          <text class="record__level">{{ record.level }}</text>
        </view>
      </view>
      <view v-if="records.length" class="caption" style="margin-top: 16rpx; text-align: center">
        仅展示最近 {{ records.length }} 条，下拉可刷新
      </view>
    </view>

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 首页：欢迎区 + 教材单元选择 + 功能入口 + 学习建议 + 最近记录。
 *
 * 教材单元选择放在首页，是因为预习/复习/模拟卷都围绕「当前单元」展开，
 * 这是全 App 的上下文入口（对应网页版的 book_selector）。
 */
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app'
import { computed, ref } from 'vue'

import { learnApi } from '../../api'
import BookPicker from '../../components/book-picker.vue'
import { catalogStore, ensureCatalog } from '../../store/catalog'
import { isVip, refreshUser, userStore } from '../../store/user'
import { scoreClass } from '../../utils/format'

const tips = [
  '先花 10 分钟朗读课文，再开始做题，语感会明显提升。',
  '错题不要只看答案，写下错因才能真正记住。',
  '每天背 5 个新词并各造 1 个句子，一周就是 35 个。',
]

const features = [
  { title: '课本预习', desc: '单元单词、核心句型与基础练习', icon: '📖', url: '/pages/preview/preview', tab: true },
  { title: '课本复习', desc: '单词复盘、句型梳理与巩固练习', icon: '🔄', url: '/pages/review/review', tab: true },
  { title: '作业中心', desc: '拍照上传，AI 逐句批改并给建议', icon: '✍️', url: '/pages/homework/homework', tab: true },
  { title: '模拟试卷', desc: '新高考六题型综合演练', icon: '📝', url: '/pages/exam/exam', vip: true },
  { title: '学情诊断', desc: '四维能力雷达图与错题归因', icon: '📊', url: '/pages/diagnosis/diagnosis', vip: true },
  { title: '会员中心', desc: '套餐与权益对比', icon: '👑', url: '/pages/membership/membership' },
]

const records = ref([])

const currentUnitLabel = computed(() => catalogStore.unit || '—')

async function loadRecords() {
  try {
    const res = await learnApi.records(5)
    records.value = (res && res.records) || []
  } catch (e) {
    records.value = []
  }
}

async function load() {
  // 冷启动时首页会先于「跳登录页」挂载一次，这时候还没有 token，
  // 发出去的请求必然 401。直接跳过，省三个来回。
  if (!userStore.token) return
  try {
    await ensureCatalog()
  } catch (err) {
    uni.showToast({ title: err.message || '教材加载失败', icon: 'none' })
  }
  refreshUser().catch(() => {})
  await loadRecords()
}

// tab 页常驻内存，onShow 每次切回来都会触发——正好用来刷新刚产生的学习记录
onShow(load)

onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})

function onCatalogChange() {
  uni.showToast({ title: `已切换到 ${currentUnitLabel.value}`, icon: 'none' })
}

function open(item) {
  if (item.tab) {
    uni.switchTab({ url: item.url })
  } else {
    uni.navigateTo({ url: item.url })
  }
}
</script>

<style scoped>
.hero {
  display: flex;
  flex-direction: column;
}

.hero__hello {
  font-size: 34rpx;
  font-weight: 700;
  color: #1f2937;
}

.hero__desc {
  display: block;
  font-size: 25rpx;
  color: #6b7280;
  margin-top: 8rpx;
  line-height: 1.6;
}

.hero__status {
  display: flex;
  flex-direction: row;
  align-items: center;
  margin-top: 20rpx;
  flex-wrap: wrap;
}

.hero__until {
  font-size: 23rpx;
  color: #9ca3af;
  margin-left: 16rpx;
}

.section-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #1f2937;
  margin: 32rpx 0 16rpx;
}

.grid {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: space-between;
}

.grid__cell {
  width: 336rpx;
  margin-bottom: 20rpx;
  padding: 24rpx 20rpx;
}

.grid__icon {
  font-size: 44rpx;
  line-height: 1.2;
}

.grid__head {
  display: flex;
  flex-direction: row;
  align-items: center;
  margin-top: 12rpx;
}

.grid__title {
  font-size: 29rpx;
  font-weight: 600;
  color: #1f2937;
  margin-right: 10rpx;
}

.grid__desc {
  display: block;
  font-size: 23rpx;
  color: #9ca3af;
  margin-top: 8rpx;
  line-height: 1.5;
}

.tip {
  display: flex;
  flex-direction: row;
  margin-bottom: 16rpx;
}

.tip:last-child {
  margin-bottom: 0;
}

.tip__index {
  width: 36rpx;
  height: 36rpx;
  line-height: 36rpx;
  text-align: center;
  border-radius: 50%;
  background: #e8f1fc;
  color: #2a78d6;
  font-size: 22rpx;
  margin-right: 16rpx;
  flex-shrink: 0;
}

.tip__text {
  flex: 1;
  font-size: 26rpx;
  color: #4b5563;
  line-height: 1.6;
}

.record {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: 20rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.record:last-of-type {
  border-bottom: none;
}

.record__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-right: 16rpx;
}

.record__module {
  font-size: 28rpx;
  color: #1f2937;
}

.record__unit {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 4rpx;
}

.record__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.record__score {
  font-size: 32rpx;
  font-weight: 700;
}

.record__level {
  font-size: 21rpx;
  color: #9ca3af;
}
</style>
