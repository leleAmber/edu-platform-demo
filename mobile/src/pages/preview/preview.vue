<template>
  <view class="page">
    <view class="caption">先掌握本单元单词与核心句型，再用基础练习检验预习效果。</view>
    <book-picker />
    <unit-study :book="catalogStore.book" :unit="catalogStore.unit" mode="preview" />
    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/** 课本预习：单元单词 / 核心句型 / 基础练习。内容只来自当前选中的教材单元。 */
import { onShow } from '@dcloudio/uni-app'

import BookPicker from '../../components/book-picker.vue'
import UnitStudy from '../../components/unit-study.vue'
import { catalogStore, ensureCatalog } from '../../store/catalog'

onShow(() => {
  ensureCatalog().catch(() => {})
})
</script>
