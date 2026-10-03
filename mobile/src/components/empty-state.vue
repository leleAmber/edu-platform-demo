<template>
  <view class="empty">
    <text class="empty__icon">{{ icon }}</text>
    <text>{{ text }}</text>
  </view>
</template>

<script setup>
defineProps({
  icon: { type: String, default: '📭' },
  text: { type: String, default: '暂无内容' },
})
</script>
