<template>
  <view class="stats">
    <view v-for="(item, index) in items" :key="index" class="stats__item">
      <text class="stats__value" :class="item.cls">{{ item.value }}</text>
      <text class="stats__label">{{ item.label }}</text>
    </view>
  </view>
</template>

<script setup>
/**
 * 统计卡片行，对应网页版的 st.metric。
 *
 * items: [{ label, value, cls? }]
 */
defineProps({
  items: { type: Array, default: () => [] },
})
</script>

<style scoped>
.stats {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
}

.stats__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20rpx 8rpx;
  background: #f7f8fc;
  border-radius: 12rpx;
  margin-right: 16rpx;
}

.stats__item:last-child {
  margin-right: 0;
}

.stats__value {
  font-size: 36rpx;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.3;
}

.stats__label {
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 4rpx;
}
</style>
