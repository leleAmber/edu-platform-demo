<template>
  <view v-if="plan" class="card">
    <view class="card__title">🗓️ {{ plan.title }}</view>
    <view class="card__caption">{{ plan.summary }}</view>

    <view v-for="day in plan.days" :key="day.day" class="plan-day">
      <view class="plan-day__head">
        <text class="plan-day__title">第 {{ day.day }} 天 · {{ day.title }}</text>
        <text class="chip chip--info">建议 {{ day.minutes }} 分钟</text>
      </view>
      <view v-for="(task, index) in day.tasks" :key="index" class="plan-day__task">
        <text class="plan-day__dot">·</text>
        <text class="plan-day__text">{{ task }}</text>
      </view>
      <view v-if="day.unit_points && day.unit_points.length" class="plan-day__points">
        对应知识点：{{ day.unit_points.join('；') }}
      </view>
    </view>

    <view v-for="(tip, index) in plan.tips" :key="`tip-${index}`" class="plan-tip">💡 {{ tip }}</view>
  </view>
</template>

<script setup>
/**
 * 学习计划卡片（预习 3 天 / 复习 7 天）。
 *
 * 结构对应 core/tutor_ai.gen_study_plan 的返回：
 * {type, title, summary, days:[{day,title,minutes,tasks[],unit_points[]}], tips[]}
 */
defineProps({
  plan: { type: Object, default: null },
})
</script>

<style scoped>
.plan-day {
  padding: 20rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.plan-day:last-of-type {
  border-bottom: none;
}

.plan-day__head {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12rpx;
}

.plan-day__title {
  flex: 1;
  font-size: 28rpx;
  font-weight: 600;
  color: #1f2937;
  margin-right: 12rpx;
}

.plan-day__task {
  display: flex;
  flex-direction: row;
  margin-bottom: 8rpx;
}

.plan-day__dot {
  color: #2a78d6;
  margin-right: 10rpx;
  font-size: 26rpx;
}

.plan-day__text {
  flex: 1;
  font-size: 26rpx;
  color: #4b5563;
  line-height: 1.6;
}

.plan-day__points {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 8rpx;
}

.plan-tip {
  font-size: 24rpx;
  color: #6b7280;
  margin-top: 16rpx;
  line-height: 1.6;
}
</style>
