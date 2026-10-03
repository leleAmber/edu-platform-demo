<template>
  <view v-if="active" class="progress">
    <view class="progress__spinner" />
    <view class="progress__text">
      <text class="progress__title">{{ text }}</text>
      <text class="progress__hint">已等待 {{ elapsedText }}，AI 批改通常需要 10~30 秒</text>
    </view>
  </view>
</template>

<script setup>
/**
 * 异步任务等待提示。
 *
 * 批改走的是「提交 → 轮询 job」的后端异步模式，UI 上必须给出真实推进感：
 * 干等的圈圈和「已等待 12 秒」对用户的耐心影响完全不同。
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import { formatDuration } from '../utils/format'

const props = defineProps({
  active: { type: Boolean, default: false },
  text: { type: String, default: 'AI 正在处理…' },
})

const seconds = ref(0)
let timer = null

function start() {
  seconds.value = 0
  stop()
  timer = setInterval(() => {
    seconds.value += 1
  }, 1000)
}

function stop() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

watch(
  () => props.active,
  (value) => (value ? start() : stop()),
  { immediate: true }
)

onUnmounted(stop)

const elapsedText = computed(() => formatDuration(seconds.value))
</script>

<style scoped>
.progress {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 32rpx 24rpx;
  background: #eef4fd;
  border-radius: 16rpx;
  margin-bottom: 24rpx;
}

.progress__spinner {
  width: 44rpx;
  height: 44rpx;
  border: 6rpx solid #c9ddf6;
  border-top-color: #2a78d6;
  border-radius: 50%;
  margin-right: 24rpx;
  animation: job-spin 0.9s linear infinite;
  flex-shrink: 0;
}

@keyframes job-spin {
  to {
    transform: rotate(360deg);
  }
}

.progress__text {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.progress__title {
  font-size: 28rpx;
  color: #1d5ba8;
  font-weight: 600;
}

.progress__hint {
  font-size: 22rpx;
  color: #6b7280;
  margin-top: 4rpx;
}
</style>
