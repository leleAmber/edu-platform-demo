<template>
  <view class="page">
    <view v-if="loading" class="loading">正在组卷…</view>

    <!-- VIP 拦截 -->
    <view v-else-if="!isVip" class="card locked">
      <text class="locked__icon">👑</text>
      <text class="locked__title">模拟试卷为 VIP 专属</text>
      <text class="locked__desc">开通会员即可解锁新高考六大题型的完整演练与 AI 阅卷。</text>
      <button class="btn mt-16" @tap="goMembership">前往会员中心</button>
    </view>

    <template v-else-if="exam">
      <book-picker :show-unit="false" @change="onBookChange" />
      <view class="caption mb-16">
        {{ exam.title }}｜当前教材：{{ catalogStore.book }}｜满分 100 分｜建议用时 {{ exam.duration }} 分钟
      </view>

      <!-- 考试结果 -->
      <template v-if="result">
        <view class="card">
          <view class="card__title">考试结果</view>
          <stat-row
            :items="[
              { label: '总分', value: `${result.total} / ${result.full_score}`, cls: scoreClass(result.total) },
              { label: '客观题', value: `${result.objective_score} 分` },
              { label: '写作', value: `${result.writing_score} 分` },
            ]"
          />
          <view class="comment">{{ result.comment }}</view>

          <view class="divider" />
          <collapse-item :title="`查看写作点评（${result.writing_notes.length} 条）`" :default-open="true">
            <text v-for="(note, index) in result.writing_notes" :key="index" class="detail__line">· {{ note }}</text>
          </collapse-item>

          <collapse-item title="查看客观题解析">
            <view v-for="(item, index) in result.details" :key="index" class="detail">
              <text class="detail__title" :class="item.is_right ? 'text-success' : 'text-danger'">
                {{ item.is_right ? '✅' : '❌' }} {{ item.question }}
              </text>
              <text class="detail__line">你的答案：{{ item.your_answer }}</text>
              <text class="detail__line">正确答案：{{ item.answer }}</text>
              <text v-if="item.explain" class="detail__line">解析：{{ item.explain }}</text>
            </view>
          </collapse-item>

          <button class="btn mt-24" @tap="restart">再考一次（换新卷）</button>
        </view>
      </template>

      <!-- 开考前须知 -->
      <template v-else-if="!started">
        <view class="card">
          <view class="card__title">开始前须知</view>
          <view class="notice">· 试卷含阅读理解、七选五、完形填空、语法填空、应用文写作、读后续写六个题型，满分 100 分</view>
          <view class="notice">· 题型种类与出题逻辑贴近新高考，仅题量缩减</view>
          <view class="notice">· 演示版本的计时功能仅作展示，不会自动交卷</view>
          <view class="notice">· 写作部分按词数、句数、连接词使用与语法错误四个角度评分</view>
          <button class="btn mt-24" @tap="started = true">开始模拟考试</button>
          <button class="btn btn--plain mt-16" @tap="reshuffle">换一套试卷</button>
        </view>
      </template>

      <!-- 答题 -->
      <template v-else>
        <view v-for="section in exam.sections" :key="section.key" class="card">
          <view class="card__title">{{ section.name }}（{{ section.score }} 分）</view>

          <!-- 应用文写作 -->
          <template v-if="section.key === 'writing_practical'">
            <text class="prompt">题目：{{ section.prompt }}</text>
            <text v-for="(req, index) in section.requirements" :key="index" class="detail__line">· {{ req }}</text>
            <textarea
              v-model="writings.writing_practical"
              class="field__textarea mt-16"
              placeholder="在此写下你的应用文…"
              placeholder-class="ph"
              maxlength="-1"
            />
          </template>

          <!-- 读后续写 -->
          <template v-else-if="section.key === 'writing_continuation'">
            <text v-if="section.passage" class="passage">{{ section.passage }}</text>
            <text class="prompt">题目：{{ section.prompt }}</text>
            <text v-for="(req, index) in section.requirements" :key="index" class="detail__line">· {{ req }}</text>
            <textarea
              v-model="writings.writing_continuation"
              class="field__textarea mt-16"
              placeholder="在此续写…"
              placeholder-class="ph"
              maxlength="-1"
            />
          </template>

          <!-- 七选五：选项在 section 级共享 -->
          <template v-else-if="section.key === 'seven_five'">
            <text class="passage">{{ section.passage }}</text>
            <view class="divider" />
            <view class="card__caption">选项</view>
            <text v-for="(opt, index) in section.options" :key="index" class="detail__line">
              {{ letter(index) }}. {{ opt }}
            </text>
            <view class="divider" />
            <view v-for="q in section.questions" :key="q.id" class="question">
              <text class="question__text">{{ q.question }}</text>
              <view class="options">
                <view
                  v-for="(opt, index) in section.options"
                  :key="index"
                  class="options__item"
                  :class="{ 'options__item--active': answers[q.id] === opt }"
                  @tap="pick(q.id, opt)"
                >
                  {{ letter(index) }}
                </view>
              </view>
            </view>
          </template>

          <!-- 阅读理解：多篇 passage -->
          <template v-else-if="section.key === 'reading'">
            <view v-for="(p, pIndex) in section.passages" :key="pIndex">
              <text class="passage">{{ p.passage }}</text>
              <view class="divider" />
              <view v-for="q in p.questions" :key="q.id" class="question">
                <text class="question__text">{{ q.question }}</text>
                <view class="options">
                  <view
                    v-for="(opt, index) in q.options"
                    :key="index"
                    class="options__item options__item--wide"
                    :class="{ 'options__item--active': answers[q.id] === opt }"
                    @tap="pick(q.id, opt)"
                  >
                    {{ letter(index) }}
                  </view>
                </view>
              </view>
            </view>
          </template>

          <!-- 完形填空 -->
          <template v-else-if="section.key === 'cloze'">
            <text class="passage">{{ section.passage }}</text>
            <view class="divider" />
            <view v-for="q in section.questions" :key="q.id" class="question">
              <text class="question__text">{{ q.question }}</text>
              <view class="options">
                <view
                  v-for="(opt, index) in q.options"
                  :key="index"
                  class="options__item"
                  :class="{ 'options__item--active': answers[q.id] === opt }"
                  @tap="pick(q.id, opt)"
                >
                  {{ letter(index) }}
                </view>
              </view>
            </view>
          </template>

          <!-- 语法填空 -->
          <template v-else-if="section.key === 'grammar_blank'">
            <text class="passage">{{ section.passage }}</text>
            <view class="divider" />
            <view v-for="q in section.questions" :key="q.id" class="question">
              <text class="question__text">{{ q.question }}</text>
              <input
                class="field__input mt-16"
                :value="answers[q.id] || ''"
                placeholder="填写答案"
                placeholder-class="ph"
                @input="onBlankInput(q.id, $event)"
              />
            </view>
          </template>
        </view>

        <button class="btn" :disabled="grading" @tap="submit">
          {{ grading ? 'AI 正在阅卷…' : '交卷' }}
        </button>
        <job-progress class="mt-16" v-if="grading" :active="true" text="AI 正在阅卷" />
      </template>
    </template>

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 模拟试卷（VIP 专属）：组卷 → 答题 → AI 阅卷。
 *
 * 题目 id 是按位置编的（r1..r8 / s1..s5 / c1..c10 / g1..g10），换卷后新旧 id
 * 完全重名。所以换教材、换试卷时必须清空作答复，否则上一份卷子的选择会被
 * 当成这一份的答案交上去——网页版踩过这个坑，这里同样处理。
 */
import { onShow } from '@dcloudio/uni-app'
import { computed, reactive, ref } from 'vue'

import { examApi, pollJob } from '../../api'
import BookPicker from '../../components/book-picker.vue'
import CollapseItem from '../../components/collapse-item.vue'
import JobProgress from '../../components/job-progress.vue'
import StatRow from '../../components/stat-row.vue'
import { catalogStore, ensureCatalog } from '../../store/catalog'
import { isVip } from '../../store/user'
import { scoreClass } from '../../utils/format'

const loading = ref(false)
const exam = ref(null)
const started = ref(false)
const grading = ref(false)
const result = ref(null)
const answers = reactive({})
const writings = reactive({ writing_practical: '', writing_continuation: '' })
const examBook = ref('')

function letter(index) {
  return String.fromCharCode(65 + index)
}

function objectiveIds(paper) {
  const ids = []
  if (!paper) return ids
  paper.sections.forEach((section) => {
    if (section.key.startsWith('writing')) return
    if (section.passages) {
      section.passages.forEach((p) => p.questions.forEach((q) => ids.push(q.id)))
    } else if (section.questions) {
      section.questions.forEach((q) => ids.push(q.id))
    }
  })
  return ids
}

function clearAnswers(paper) {
  objectiveIds(paper).forEach((id) => delete answers[id])
  writings.writing_practical = ''
  writings.writing_continuation = ''
}

function reset() {
  started.value = false
  result.value = null
}

function pick(qid, option) {
  answers[qid] = answers[qid] === option ? '' : option
}

function onBlankInput(qid, event) {
  answers[qid] = event.detail.value
}

async function load(refresh = false) {
  loading.value = true
  try {
    await ensureCatalog()
    const paper = await examApi.get(catalogStore.book, refresh)
    // 换卷/换教材前先按旧卷清作答
    clearAnswers(exam.value)
    exam.value = paper
    examBook.value = catalogStore.book
    reset()
  } catch (err) {
    uni.showToast({ title: err.message || '组卷失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function onBookChange() {
  if (catalogStore.book !== examBook.value) load()
}

function reshuffle() {
  load(true)
}

function restart() {
  load(true)
}

async function submit() {
  const hasAnswer = Object.values(answers).some((value) => value) || writings.writing_practical || writings.writing_continuation
  if (!hasAnswer) {
    uni.showToast({ title: '还没有作答，请完成后交卷', icon: 'none' })
    return
  }
  grading.value = true
  try {
    const { job_id } = await examApi.grade(catalogStore.book, { ...answers }, { ...writings })
    result.value = await pollJob(job_id)
    uni.pageScrollTo({ scrollTop: 0, duration: 200 })
  } catch (err) {
    uni.showToast({ title: err.message || '阅卷失败', icon: 'none' })
  } finally {
    grading.value = false
  }
}

function goMembership() {
  uni.navigateTo({ url: '/pages/membership/membership' })
}

onShow(() => {
  if (isVip.value && !exam.value) load()
})
</script>

<style scoped>
.locked {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60rpx 32rpx;
}

.locked__icon {
  font-size: 80rpx;
}

.locked__title {
  font-size: 32rpx;
  font-weight: 700;
  color: #b7791f;
  margin-top: 16rpx;
}

.locked__desc {
  font-size: 25rpx;
  color: #6b7280;
  margin-top: 12rpx;
  text-align: center;
  line-height: 1.6;
}

.notice {
  font-size: 26rpx;
  color: #4b5563;
  line-height: 1.8;
}

.passage {
  display: block;
  font-size: 27rpx;
  color: #374151;
  line-height: 1.8;
  text-align: justify;
}

.prompt {
  display: block;
  font-size: 27rpx;
  color: #1f2937;
  line-height: 1.7;
  margin-bottom: 8rpx;
}

.question {
  padding: 24rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.question:last-child {
  border-bottom: none;
}

.question__text {
  display: block;
  font-size: 27rpx;
  color: #1f2937;
  line-height: 1.6;
  margin-bottom: 16rpx;
}

.options {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
}

.options__item {
  width: 68rpx;
  height: 68rpx;
  line-height: 68rpx;
  text-align: center;
  border-radius: 50%;
  background: #f1f3f8;
  color: #6b7280;
  font-size: 26rpx;
  margin: 0 16rpx 16rpx 0;
}

.options__item--wide {
  width: auto;
  min-width: 68rpx;
  padding: 0 20rpx;
  border-radius: 34rpx;
}

.options__item--active {
  background: #2a78d6;
  color: #ffffff;
}

.comment {
  margin-top: 20rpx;
  font-size: 27rpx;
  color: #1f2937;
  line-height: 1.7;
}

.detail {
  padding: 16rpx 0;
  border-bottom: 2rpx solid #f3f4f8;
}

.detail:last-child {
  border-bottom: none;
}

.detail__title {
  display: block;
  font-size: 26rpx;
  line-height: 1.5;
  margin-bottom: 6rpx;
}

.detail__line {
  display: block;
  font-size: 24rpx;
  color: #6b7280;
  line-height: 1.7;
}

.ph {
  color: #c0c4cc;
}
</style>
