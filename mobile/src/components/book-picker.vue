<template>
  <view class="card picker">
    <view class="picker__row">
      <text class="picker__label">当前教材</text>
      <picker mode="selector" :range="labels" :value="bookIndex" @change="onBookChange">
        <view class="picker__value">
          <text>{{ currentBookLabel }}</text>
          <text class="picker__arrow">▾</text>
        </view>
      </picker>
    </view>

    <view v-if="showUnit" class="divider" />

    <view v-if="showUnit" class="picker__row">
      <text class="picker__label">当前单元</text>
      <picker
        mode="selector"
        :range="catalogStore.units"
        :value="unitIndex"
        :disabled="!catalogStore.units.length"
        @change="onUnitChange"
      >
        <view class="picker__value">
          <text>{{ catalogStore.unit || '暂无单元' }}</text>
          <text class="picker__arrow">▾</text>
        </view>
      </picker>
    </view>
  </view>
</template>

<script setup>
/**
 * 教材 / 单元选择器。
 *
 * 换教材会把单元重置为新书首单元 —— 跨书残留旧单元会取不到内容，
 * 与网页版 components/book_selector.py 的行为一致。
 */
import { computed } from 'vue'

import { bookLabel, catalogStore, selectBook, selectUnit } from '../store/catalog'

const props = defineProps({
  showUnit: { type: Boolean, default: true },
})

const emit = defineEmits(['change'])

const labels = computed(() => catalogStore.books.map((b) => bookLabel(b.key)))
const currentBookLabel = computed(() => bookLabel(catalogStore.book))
const bookIndex = computed(() => Math.max(0, catalogStore.books.findIndex((b) => b.key === catalogStore.book)))
const unitIndex = computed(() => Math.max(0, catalogStore.units.indexOf(catalogStore.unit)))

async function onBookChange(event) {
  const index = Number(event.detail.value)
  const target = catalogStore.books[index]
  if (!target || target.key === catalogStore.book) return
  await selectBook(target.key)
  emit('change', { book: catalogStore.book, unit: catalogStore.unit })
}

function onUnitChange(event) {
  const index = Number(event.detail.value)
  const unit = catalogStore.units[index]
  if (!unit || unit === catalogStore.unit) return
  selectUnit(unit)
  emit('change', { book: catalogStore.book, unit: catalogStore.unit })
}
</script>

<style scoped>
.picker {
  padding: 8rpx 24rpx;
}

.picker__row {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  min-height: 88rpx;
}

.picker__label {
  font-size: 26rpx;
  color: #6b7280;
  flex-shrink: 0;
  margin-right: 16rpx;
}

.picker__value {
  display: flex;
  flex-direction: row;
  align-items: center;
  font-size: 28rpx;
  color: #2a78d6;
  max-width: 460rpx;
}

.picker__arrow {
  margin-left: 8rpx;
  font-size: 22rpx;
  color: #9ca3af;
}
</style>
