<template>
  <view>
    <view v-if="loading" class="loading">正在加载单元内容…</view>

    <template v-else-if="content">
      <view class="caption mb-16">单元主题：{{ content.theme || '—' }}</view>

      <!-- 分段控件，替代网页版的 st.tabs（手机上是点按切换，不是左右滑动，
           因为选项卡里还有答题交互，横滑容易误触） -->
      <view class="segments">
        <view
          v-for="tab in tabs"
          :key="tab.key"
          class="segments__item"
          :class="{ 'segments__item--active': active === tab.key }"
          @tap="active = tab.key"
        >
          {{ tab.label }}
        </view>
      </view>

      <!-- 单词 -->
      <view v-if="active === 'words'">
        <view v-if="isReview" class="card">
          <stat-row
            :items="[
              { label: '已掌握词汇', value: `${stats.mastered} 个` },
              { label: '待巩固词汇', value: `${stats.to_review} 个` },
            ]"
          />
        </view>

        <view v-if="!words.length" class="card">
          <empty-state icon="📖" text="本单元暂无单词数据，请先运行教材解析脚本生成内容。" />
        </view>

        <view v-else class="card">
          <view class="card__title">{{ isReview ? `完整单词表（${words.length} 个）` : `单元单词（${words.length} 个）` }}</view>
          <view class="card__caption">
            {{ isReview ? '复盘时遮住释义自测，比反复看更有效。' : '建议每个词各造一个句子。' }}
          </view>
          <view class="divider" />
          <view v-for="item in words" :key="item.index" class="word">
            <view class="word__head">
              <text class="word__text">{{ item.word }}</text>
              <text v-if="item.pos" class="word__pos">{{ item.pos }}</text>
            </view>
            <text class="word__explain">{{ item.explain }}</text>
            <text v-if="item.sentence" class="word__sentence">{{ item.sentence }}</text>
          </view>
        </view>
      </view>

      <!-- 句型 -->
      <view v-else-if="active === 'patterns'">
        <view v-if="!patterns.length" class="card">
          <empty-state icon="🧩" text="本单元暂无句型数据。" />
        </view>
        <view v-else class="card">
          <view class="card__title">{{ isReview ? '重点句型梳理' : '核心句型' }}</view>
          <view class="divider" />
          <collapse-item
            v-for="(item, index) in patterns"
            :key="index"
            :title="`句型 ${index + 1}｜${truncate(item.pattern, 22)}`"
            :default-open="index === 0"
          >
            <text class="pattern__line"><text class="pattern__label">句型：</text>{{ item.pattern }}</text>
            <text v-if="item.explain" class="pattern__line"><text class="pattern__label">讲解：</text>{{ item.explain }}</text>
            <text v-if="item.example" class="pattern__line"><text class="pattern__label">例句：</text>{{ item.example }}</text>
            <text v-if="item.translation" class="pattern__translation">参考翻译：{{ item.translation }}</text>
          </collapse-item>
        </view>
      </view>

      <!-- 练习 -->
      <view v-else class="card">
        <view class="row row--between mb-16">
          <text class="card__title">{{ isReview ? '巩固练习' : '基础练习' }}（共 {{ questions.length }} 题）</text>
          <text v-if="questions.length" class="link" @tap="refresh">换一批</text>
        </view>

        <quiz-panel
          ref="panelRef"
          :questions="questions"
          :book="book"
          :unit="unit"
          :quiz-type="quizType"
          @graded="onGraded"
        >
          <template #after-result>
            <button class="btn btn--ghost mt-24" :disabled="planning" @tap="makePlan">
              {{ planning ? '生成中…' : `生成${isReview ? '复习' : '预习'}学习计划` }}
            </button>
          </template>
        </quiz-panel>

        <plan-card v-if="plan" class="mt-24" :plan="plan" />
      </view>
    </template>
  </view>
</template>

<script setup>
/**
 * 单元学习主体：单词 / 句型 / 练习 三段。
 *
 * 「课本预习」与「课本复习」的数据结构与交互几乎相同，差别只在文案与
 * 复习页多一组词汇统计，所以合成一个组件用 mode 区分，
 * 避免两个页面各维护一份几乎一样的代码。
 */
import { computed, ref, watch } from 'vue'

import { bookApi, learnApi } from '../api'
import { normalizeQuestions, normalizeWords, truncate } from '../utils/format'
import CollapseItem from './collapse-item.vue'
import EmptyState from './empty-state.vue'
import PlanCard from './plan-card.vue'
import QuizPanel from './quiz-panel.vue'
import StatRow from './stat-row.vue'

const props = defineProps({
  book: { type: String, default: '' },
  unit: { type: String, default: '' },
  mode: { type: String, default: 'preview' }, // preview | review
})

const emit = defineEmits(['graded'])

const loading = ref(false)
const content = ref(null)
const questions = ref([])
const active = ref('words')
const plan = ref(null)
const planning = ref(false)
const panelRef = ref(null)

const isReview = computed(() => props.mode === 'review')
const quizType = computed(() => props.mode)

const tabs = computed(() =>
  isReview.value
    ? [
        { key: 'words', label: '单词复盘' },
        { key: 'patterns', label: '重点句型梳理' },
        { key: 'practice', label: '巩固练习' },
      ]
    : [
        { key: 'words', label: '单元单词' },
        { key: 'patterns', label: '核心句型' },
        { key: 'practice', label: '基础练习' },
      ]
)

const words = computed(() => normalizeWords(content.value && content.value.words))
const patterns = computed(() => (content.value && content.value.sentence_patterns) || [])
const stats = computed(() => {
  const raw = (content.value && content.value.vocab_stats) || {}
  return { mastered: raw.mastered || 0, to_review: raw.to_review || words.value.length }
})

async function load() {
  if (!props.book || !props.unit) return
  loading.value = true
  plan.value = null
  try {
    const res = await bookApi.unitContent(props.book, props.unit)
    content.value = res
    questions.value = normalizeQuestions(res[`${quizType.value}_quiz`])
    if (panelRef.value) panelRef.value.reset()
  } catch (err) {
    uni.showToast({ title: err.message || '加载失败', icon: 'none' })
    content.value = null
    questions.value = []
  } finally {
    loading.value = false
  }
}

/** 换一批题目：让服务端清掉抽题缓存后重新随机。 */
async function refresh() {
  try {
    const res = await bookApi.refreshQuiz(props.book, props.unit, quizType.value)
    questions.value = normalizeQuestions(res && res.quiz)
    if (panelRef.value) panelRef.value.reset()
    uni.showToast({ title: '已换一批题目', icon: 'none' })
  } catch (err) {
    uni.showToast({ title: err.message || '换题失败', icon: 'none' })
  }
}

function onGraded(result) {
  emit('graded', result)
}

async function makePlan() {
  planning.value = true
  try {
    plan.value = await learnApi.studyPlan(quizType.value, props.book, props.unit)
  } catch (err) {
    uni.showToast({ title: err.message || '无法生成学习计划', icon: 'none' })
  } finally {
    planning.value = false
  }
}

watch(() => [props.book, props.unit], load, { immediate: true })
</script>

<style scoped>
.segments {
  display: flex;
  flex-direction: row;
  background: #eceff6;
  border-radius: 12rpx;
  padding: 6rpx;
  margin-bottom: 24rpx;
}

.segments__item {
  flex: 1;
  text-align: center;
  font-size: 26rpx;
  color: #6b7280;
  padding: 16rpx 0;
  border-radius: 10rpx;
}

.segments__item--active {
  background: #ffffff;
  color: #2a78d6;
  font-weight: 600;
}

.word {
  padding: 20rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.word:last-child {
  border-bottom: none;
}

.word__head {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  margin-bottom: 6rpx;
}

.word__text {
  font-size: 32rpx;
  font-weight: 600;
  color: #1f2937;
  margin-right: 12rpx;
}

.word__pos {
  font-size: 22rpx;
  color: #2a78d6;
  background: #e8f1fc;
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
}

.word__explain {
  display: block;
  font-size: 26rpx;
  color: #4b5563;
  line-height: 1.6;
}

.word__sentence {
  display: block;
  font-size: 24rpx;
  color: #9ca3af;
  margin-top: 6rpx;
  line-height: 1.6;
}

.pattern__line {
  display: block;
  font-size: 26rpx;
  color: #4b5563;
  line-height: 1.7;
  margin-bottom: 6rpx;
}

.pattern__label {
  color: #9ca3af;
}

.pattern__translation {
  display: block;
  font-size: 23rpx;
  color: #9ca3af;
  margin-top: 6rpx;
}

.link {
  font-size: 26rpx;
  color: #2a78d6;
}
</style>
