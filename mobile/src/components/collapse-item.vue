<template>
  <view class="collapse">
    <view class="collapse__head" @tap="open = !open">
      <text class="collapse__title">{{ title }}</text>
      <text class="collapse__arrow" :class="{ 'collapse__arrow--open': open }">▾</text>
    </view>
    <view v-if="open" class="collapse__body">
      <slot />
    </view>
  </view>
</template>

<script setup>
/**
 * 折叠面板，替代网页版的 st.expander。
 *
 * 手机屏幕窄，一屏塞不下 8 道题的解析，默认收起、点开再看。
 */
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  defaultOpen: { type: Boolean, default: false },
})

const open = ref(props.defaultOpen)
</script>

<style scoped>
.collapse {
  border-bottom: 2rpx solid #eef0f5;
}

.collapse:last-child {
  border-bottom: none;
}

.collapse__head {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: 24rpx 0;
  min-height: 88rpx;
}

.collapse__title {
  flex: 1;
  font-size: 28rpx;
  color: #1f2937;
  margin-right: 16rpx;
}

.collapse__arrow {
  font-size: 24rpx;
  color: #9ca3af;
  transition: transform 0.2s;
}

.collapse__arrow--open {
  transform: rotate(180deg);
}

.collapse__body {
  padding: 0 0 24rpx 0;
}
</style>
