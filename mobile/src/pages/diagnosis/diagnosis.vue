<template>
  <view class="page">
    <view class="caption">基于你的练习与批改记录，从词汇、句法、语篇、写作四个维度给出诊断。</view>

    <view v-if="loading" class="loading">正在分析学情…</view>

    <!-- VIP 拦截 -->
    <view v-else-if="!isVip" class="card locked">
      <text class="locked__icon">📊</text>
      <text class="locked__title">学情诊断为 VIP 专属</text>
      <text class="locked__desc">开通会员即可查看四维能力雷达图、错题归因与个性化改进建议。</text>
      <button class="btn mt-16" @tap="goMembership">前往会员中心</button>
    </view>

    <template v-else-if="data">
      <!-- 雷达图 -->
      <view class="card">
        <view class="card__title">四维能力雷达图</view>
        <radar-chart
          :categories="data.radar.categories"
          :values="data.radar.values"
          :max="data.radar.max"
          :excellent-line="data.radar.excellent_line"
        />
        <view class="caption" style="text-align: center">橙色虚线为 85 分优秀线</view>
      </view>

      <!-- 摘要 -->
      <view class="card">
        <view class="card__title">学情诊断摘要</view>
        <stat-row
          :items="[
            { label: '优势维度', value: data.strongest },
            { label: '薄弱维度', value: data.weakest },
          ]"
        />

        <view class="divider" />
        <view class="card__caption">各维度得分</view>
        <view v-for="(label, key) in data.dimension_labels" :key="key" class="dim">
          <text class="dim__label">{{ label }}</text>
          <text class="dim__value" :class="scoreClass(data.dimensions[key])">{{ data.dimensions[key] }} 分</text>
        </view>

        <view class="divider" />
        <view class="card__caption">AI 学习改进建议</view>
        <view v-for="(tip, index) in data.suggestions" :key="index" class="tip">
          <text class="tip__index">{{ index + 1 }}</text>
          <text class="tip__text">{{ tip }}</text>
        </view>

        <view class="caption" style="margin-top: 16rpx">
          本次诊断基于最近 {{ data.sample_count }} 条学习记录，平均分 {{ data.average }} 分。
        </view>
      </view>

      <!-- 错题归因 -->
      <view class="card">
        <view class="card__title">错题归因</view>
        <view class="card__caption">占比越高说明该维度越需要优先突破。</view>
        <view v-for="(ratio, dimension) in data.error_ratio" :key="dimension" class="ratio">
          <view class="row row--between">
            <text class="ratio__name">{{ dimension }}</text>
            <text class="ratio__value">{{ ratio }}%</text>
          </view>
          <view class="ratio__bar">
            <view class="ratio__fill" :style="{ width: `${Math.min(ratio, 100)}%` }" :class="ratioFillClass(ratio)" />
          </view>
        </view>
      </view>

      <!-- 学习进度 -->
      <view class="card">
        <view class="card__title">学习进度统计</view>
        <view v-if="!data.progress.values.length" class="empty">
          <text class="empty__icon">📈</text>
          <text>还没有学习记录，完成练习后这里会显示进度曲线。</text>
        </view>
        <template v-else>
          <bar-chart
            :labels="data.progress.labels"
            :values="data.progress.values"
            :excellent-line="data.progress.excellent_line"
          />
          <view class="caption" style="text-align: center">
            共记录 {{ data.progress.total_count }} 次练习
          </view>
        </template>
      </view>
    </template>

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 学情诊断（VIP 专属）。
 *
 * 雷达图和柱状图在网页版是 plotly，小程序里换成自绘 canvas 组件。
 * 图表数据（categories/values/excellent_line）由后端一并给出，
 * 客户端不做任何计算——两端的图形永远对得上。
 */
import { onShow } from '@dcloudio/uni-app'
import { ref } from 'vue'

import { diagnosisApi } from '../../api'
import BarChart from '../../components/bar-chart.vue'
import RadarChart from '../../components/radar-chart.vue'
import StatRow from '../../components/stat-row.vue'
import { isVip } from '../../store/user'
import { scoreClass } from '../../utils/format'

const loading = ref(false)
const data = ref(null)

async function load() {
  if (!isVip.value) return
  loading.value = true
  try {
    data.value = await diagnosisApi.get()
  } catch (err) {
    uni.showToast({ title: err.message || '诊断失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onShow(load)

function ratioFillClass(ratio) {
  if (ratio >= 30) return 'ratio__fill--danger'
  if (ratio >= 20) return 'ratio__fill--warning'
  return 'ratio__fill--success'
}

function goMembership() {
  uni.navigateTo({ url: '/pages/membership/membership' })
}
</script>

<style scoped>
.locked {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 32rpx;
}

.locked__icon {
  font-size: 80rpx;
}

.locked__title {
  font-size: 32rpx;
  font-weight: 700;
  color: #b7791f;
  margin-top: 16rpx;
}

.locked__desc {
  font-size: 25rpx;
  color: #6b7280;
  margin-top: 12rpx;
  text-align: center;
  line-height: 1.6;
}

.dim {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  padding: 12rpx 0;
}

.dim__label {
  font-size: 26rpx;
  color: #4b5563;
}

.dim__value {
  font-size: 27rpx;
  font-weight: 600;
}

.tip {
  display: flex;
  flex-direction: row;
  margin-top: 16rpx;
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
  margin-right: 12rpx;
  flex-shrink: 0;
}

.tip__text {
  flex: 1;
  font-size: 25rpx;
  color: #4b5563;
  line-height: 1.7;
}

.ratio {
  margin-top: 20rpx;
}

.ratio__name {
  font-size: 26rpx;
  color: #4b5563;
}

.ratio__value {
  font-size: 26rpx;
  font-weight: 600;
  color: #1f2937;
}

.ratio__bar {
  height: 14rpx;
  border-radius: 7rpx;
  background: #eef0f5;
  margin-top: 10rpx;
  overflow: hidden;
}

.ratio__fill {
  height: 14rpx;
  border-radius: 7rpx;
}

.ratio__fill--danger { background: #dc2626; }
.ratio__fill--warning { background: #e08a3c; }
.ratio__fill--success { background: #1f9d55; }
</style>
