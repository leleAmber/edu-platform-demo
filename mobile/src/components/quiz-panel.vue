<template>
  <view>
    <view v-if="!questions.length">
      <empty-state icon="📝" text="本单元暂无练习题（题库不足）。生成后会自动从题库抽取。" />
    </view>

    <template v-else>
      <view v-for="(item, index) in questions" :key="item.id" class="quiz">
        <view class="quiz__head">
          <text class="quiz__index">{{ index + 1 }}</text>
          <text class="quiz__question">{{ item.question }}</text>
        </view>
        <view
          v-for="(option, optionIndex) in item.options"
          :key="optionIndex"
          class="quiz__option"
          :class="{ 'quiz__option--active': answers[index] === option }"
          @tap="choose(index, option)"
        >
          <text class="quiz__letter">{{ letter(optionIndex) }}</text>
          <text class="quiz__option-text">{{ option }}</text>
        </view>
      </view>

      <button class="btn mt-24" :disabled="submitting" @tap="submit">
        {{ submitting ? '正在批改…' : '提交答案' }}
      </button>
      <view class="caption" style="margin-top: 12rpx; text-align: center">
        已作答 {{ answeredCount }} / {{ questions.length }} 题
      </view>

      <!-- 批改结果 -->
      <view v-if="result" class="card mt-24">
        <view class="card__title">批改结果</view>
        <stat-row
          :items="[
            { label: '客观得分', value: `${result.score} 分` },
            { label: '答对题数', value: `${result.correct_count} / ${result.total}` },
            { label: 'AI 掌握度', value: `${result.mastery} 分`, cls: scoreClass(result.mastery) },
          ]"
        />
        <view class="mt-16">
          <text class="chip" :class="`chip--${levelChip(result.level)}`">本次掌握度：{{ result.level }}</text>
        </view>

        <view class="divider" />

        <collapse-item title="查看逐题解析">
          <view v-for="item in result.details" :key="item.index" class="detail">
            <text class="detail__title" :class="item.is_right ? 'text-success' : 'text-danger'">
              {{ item.is_right ? '✅' : '❌' }} {{ item.index }}. {{ item.question }}
            </text>
            <text class="detail__line">
              你的答案：{{ optionLetter(questions[item.index - 1]?.options, item.your_answer) || '未作答' }}
            </text>
            <text class="detail__line">
              正确答案：{{ optionLetter(questions[item.index - 1]?.options, item.answer) }}
            </text>
            <text v-if="item.explain" class="detail__line">解析：{{ item.explain }}</text>
          </view>
        </collapse-item>

        <slot name="after-result" :result="result" />
      </view>
    </template>
  </view>
</template>

<script setup>
/**
 * 预习 / 复习练习题面板（答题 + 服务端批改 + 结果展示）。
 *
 * 批改必须在服务端做：题目下发时已经脱敏，客户端没有答案可比。
 */
import { computed, ref, watch } from 'vue'

import { learnApi } from '../api'
import { levelChip, optionLetter, scoreClass } from '../utils/format'
import CollapseItem from './collapse-item.vue'
import EmptyState from './empty-state.vue'
import StatRow from './stat-row.vue'

const props = defineProps({
  questions: { type: Array, default: () => [] },
  book: { type: String, default: '' },
  unit: { type: String, default: '' },
  quizType: { type: String, default: 'preview' },
})

const emit = defineEmits(['graded'])

const answers = ref({})
const result = ref(null)
const submitting = ref(false)

const answeredCount = computed(() => Object.values(answers.value).filter(Boolean).length)

// 换单元/换一批题目时清空作答与上一次的结果，否则旧答案会串到新题上
watch(
  () => [props.book, props.unit, props.quizType, props.questions],
  () => {
    answers.value = {}
    result.value = null
  }
)

function letter(index) {
  return String.fromCharCode(65 + index)
}

function choose(index, option) {
  answers.value = { ...answers.value, [index]: option }
}

async function submit() {
  if (answeredCount.value < props.questions.length) {
    uni.showToast({ title: '还有题目没有作答', icon: 'none' })
    return
  }
  submitting.value = true
  try {
    const res = await learnApi.gradeQuiz(props.book, props.unit, props.quizType, answers.value)
    result.value = res
    emit('graded', res)
  } catch (err) {
    uni.showToast({ title: err.message || '批改失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

defineExpose({ reset: () => { answers.value = {}; result.value = null } })
</script>

<style scoped>
.quiz {
  padding: 24rpx 0;
  border-bottom: 2rpx solid #eef0f5;
}

.quiz:last-of-type {
  border-bottom: none;
}

.quiz__head {
  display: flex;
  flex-direction: row;
  margin-bottom: 16rpx;
}

.quiz__index {
  width: 40rpx;
  height: 40rpx;
  line-height: 40rpx;
  text-align: center;
  border-radius: 50%;
  background: #e8f1fc;
  color: #2a78d6;
  font-size: 22rpx;
  margin-right: 12rpx;
  flex-shrink: 0;
}

.quiz__question {
  flex: 1;
  font-size: 29rpx;
  color: #1f2937;
  line-height: 1.5;
}

.quiz__option {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 20rpx 20rpx;
  background: #f7f8fc;
  border-radius: 12rpx;
  margin-bottom: 12rpx;
  border: 2rpx solid transparent;
}

.quiz__option--active {
  background: #e8f1fc;
  border-color: #2a78d6;
}

.quiz__letter {
  width: 40rpx;
  height: 40rpx;
  line-height: 40rpx;
  text-align: center;
  border-radius: 50%;
  background: #ffffff;
  color: #6b7280;
  font-size: 22rpx;
  margin-right: 16rpx;
  flex-shrink: 0;
}

.quiz__option--active .quiz__letter {
  background: #2a78d6;
  color: #ffffff;
}

.quiz__option-text {
  flex: 1;
  font-size: 27rpx;
  color: #1f2937;
}

.detail {
  display: flex;
  flex-direction: column;
  padding: 16rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.detail:last-child {
  border-bottom: none;
}

.detail__title {
  font-size: 27rpx;
  line-height: 1.5;
  margin-bottom: 6rpx;
}

.detail__line {
  font-size: 24rpx;
  color: #6b7280;
  line-height: 1.6;
}
</style>
