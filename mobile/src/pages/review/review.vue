<template>
  <view class="page">
    <view class="caption">复盘本单元单词与重点句型，再用巩固练习查漏补缺。</view>
    <book-picker />
    <unit-study :book="catalogStore.book" :unit="catalogStore.unit" mode="review" />
    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/** 课本复习：单词复盘 / 重点句型梳理 / 巩固练习。与预习页共用 unit-study 组件。 */
import { onShow } from '@dcloudio/uni-app'

import BookPicker from '../../components/book-picker.vue'
import UnitStudy from '../../components/unit-study.vue'
import { catalogStore, ensureCatalog } from '../../store/catalog'

onShow(() => {
  ensureCatalog().catch(() => {})
})
</script>
