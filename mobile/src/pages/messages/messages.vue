<template>
  <view class="page">
    <view class="caption">有问题或建议都可以留言，管理员回复后会显示在下方。</view>

    <!-- 提交留言 -->
    <view class="card mt-16">
      <view class="card__title">我要留言</view>
      <textarea
        v-model="content"
        class="field__textarea"
        placeholder="请输入你的问题或建议（最多 2000 字）"
        placeholder-class="ph"
        maxlength="2000"
      />
      <button class="btn mt-16" :disabled="sending" @tap="submit">
        {{ sending ? '提交中…' : '提交留言' }}
      </button>
    </view>

    <!-- 留言列表 -->
    <view class="section-title">
      我的留言
      <text v-if="pending" class="chip chip--warning" style="margin-left: 12rpx">{{ pending }} 条待回复</text>
    </view>

    <view v-if="loading" class="loading">正在加载…</view>
    <view v-else-if="!messages.length" class="card">
      <empty-state icon="💬" text="还没有留言记录。" />
    </view>
    <view v-else class="card">
      <view v-for="item in messages" :key="item.msg_id" class="msg">
        <view class="row row--between">
          <text class="msg__id">{{ item.msg_id }}</text>
          <text class="chip" :class="item.is_replied ? 'chip--success' : 'chip--warning'">
            {{ item.is_replied ? '已回复' : '待回复' }}
          </text>
        </view>
        <text class="msg__content">{{ item.content }}</text>
        <text class="msg__time">{{ item.created_at }}</text>
        <view v-if="item.is_replied" class="msg__reply">
          <text class="msg__reply-label">管理员回复</text>
          <text class="msg__reply-text">{{ item.reply }}</text>
          <text class="msg__time">{{ item.replied_at }}</text>
        </view>
      </view>
    </view>

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 客服留言：提交 + 查看回复。
 *
 * 与网页版共用 messages 表，后台在网页版处理，学生端在手机上问。
 */
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app'
import { computed, ref } from 'vue'

import { messageApi } from '../../api'
import EmptyState from '../../components/empty-state.vue'
import { userStore } from '../../store/user'

const content = ref('')
const messages = ref([])
const loading = ref(false)
const sending = ref(false)

const pending = computed(() => messages.value.filter((item) => !item.is_replied).length)

async function load() {
  if (!userStore.token) return
  loading.value = true
  try {
    const res = await messageApi.list()
    messages.value = (res && res.messages) || []
  } catch (err) {
    uni.showToast({ title: err.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onShow(load)

onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})

async function submit() {
  const value = content.value.trim()
  if (!value) {
    uni.showToast({ title: '请先输入留言内容', icon: 'none' })
    return
  }
  sending.value = true
  try {
    await messageApi.create(value)
    content.value = ''
    uni.showToast({ title: '留言已提交', icon: 'success' })
    await load()
  } catch (err) {
    uni.showToast({ title: err.message || '提交失败', icon: 'none' })
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.section-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #1f2937;
  margin: 32rpx 0 16rpx;
}

.msg {
  padding: 24rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.msg:last-child {
  border-bottom: none;
}

.msg__id {
  font-size: 23rpx;
  color: #9ca3af;
}

.msg__content {
  display: block;
  font-size: 27rpx;
  color: #1f2937;
  line-height: 1.7;
  margin-top: 12rpx;
}

.msg__time {
  display: block;
  font-size: 22rpx;
  color: #9ca3af;
  margin-top: 8rpx;
}

.msg__reply {
  margin-top: 16rpx;
  padding: 20rpx;
  background: #eef4fd;
  border-radius: 12rpx;
}

.msg__reply-label {
  display: block;
  font-size: 23rpx;
  color: #1d5ba8;
  font-weight: 600;
  margin-bottom: 8rpx;
}

.msg__reply-text {
  display: block;
  font-size: 26rpx;
  color: #374151;
  line-height: 1.7;
}

.ph {
  color: #c0c4cc;
}
</style>
