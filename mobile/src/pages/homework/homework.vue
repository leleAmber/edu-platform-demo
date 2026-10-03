<template>
  <view class="page">
    <view class="caption">拍照上传或直接粘贴作业，AI 识别后逐句批改（作文 / 选择题 / 填空题均可）。</view>

    <!-- 录入 -->
    <view class="card mt-16">
      <view class="card__title">作业录入</view>
      <textarea
        v-model="text"
        class="field__textarea"
        placeholder="键盘粘贴作业，或上传图片后点「识别图片」自动填入"
        placeholder-class="ph"
        maxlength="-1"
      />
      <view v-if="fromImage" class="warn">
        ⚠️ 图片识别结果可能有误、顺序可能错乱，批改前请先检查并修正上面的内容。
      </view>

      <view class="divider" />

      <view class="row row--between mb-16">
        <text class="card__title" style="margin-bottom: 0">📷 作业图片</text>
        <text class="caption">最多 5 张</text>
      </view>
      <view class="caption">拍照小贴士：正对纸张、光线充足、避免反光和阴影，字写深一点识别更准。</view>

      <view class="thumbs">
        <view v-for="(path, index) in images" :key="index" class="thumbs__item">
          <image class="thumbs__img" :src="path" mode="aspectFill" @tap="preview(index)" />
          <text class="thumbs__del" @tap="removeImage(index)">×</text>
        </view>
        <view v-if="images.length < 5" class="thumbs__add" @tap="chooseImages">＋</view>
      </view>

      <button class="btn btn--plain mt-16" :disabled="recognizing || !images.length" @tap="recognize">
        {{ recognizing ? '识别中…' : '🔍 识别图片' }}
      </button>

      <job-progress v-if="recognizing" :active="true" :text="`正在识别第 ${recognizeIndex} / ${images.length} 张图片`" />

      <button class="btn mt-16" :disabled="grading" @tap="grade">
        {{ grading ? '批改中…' : '提交 AI 批改' }}
      </button>
    </view>

    <job-progress v-if="grading" :active="true" text="AI 正在逐句批改" />

    <!-- 结果 -->
    <view v-if="result" class="card">
      <view class="card__title">批改结果</view>
      <view class="caption">批改引擎：{{ result.source || '—' }}</view>
      <view v-if="result.note" class="warn warn--info">{{ result.note }}</view>

      <view class="mt-16">
        <stat-row
          :items="[
            { label: '总分', value: `${result.total_score} 分`, cls: scoreClass(result.total_score) },
            { label: '答对', value: result.right_count, cls: 'text-success' },
            { label: '待修改', value: result.wrong_count, cls: 'text-danger' },
          ]"
        />
      </view>

      <!-- 免费用户：逐题解析由服务端剥离，这里只做引导 -->
      <template v-if="result.locked">
        <view class="divider" />
        <view class="locked">
          <text class="locked__title">👑 逐题解析与修改建议为 VIP 权益</text>
          <text class="locked__desc">开通会员后可查看每一句的错因、参考答案与 AI 总评。</text>
          <button class="btn mt-16" @tap="goMembership">前往会员中心开通</button>
        </view>
      </template>

      <template v-else>
        <view v-if="result.comment" class="comment">AI 评语：{{ result.comment }}</view>

        <view class="divider" />
        <view v-if="!result.details.length" class="text-success" style="padding: 16rpx 0">
          未检测到明显问题，继续保持！
        </view>
        <template v-else>
          <view class="caption mb-16">共 {{ result.details.length }} 条，点击展开查看逐题解析。</view>
          <collapse-item v-for="item in result.details" :key="item.index" :title="detailTitle(item)">
            <text v-if="item.question" class="detail__line"><text class="detail__label">题目/原句：</text>{{ item.question }}</text>
            <text v-if="item.your_answer" class="detail__line"><text class="detail__label">你的作答：</text>{{ item.your_answer }}</text>
            <text v-if="item.correct_answer" class="detail__line"><text class="detail__label">参考答案：</text>{{ item.correct_answer }}</text>
            <text v-if="item.explain" class="detail__line"><text class="detail__label">解析：</text>{{ item.explain }}</text>
          </collapse-item>
        </template>

        <template v-if="errorTypes.length">
          <view class="divider" />
          <view class="card__title">错误类型分布</view>
          <view v-for="item in errorTypes" :key="item.name" class="errtype">
            <text>{{ item.name }}</text>
            <text class="errtype__count">{{ item.count }} 处</text>
          </view>
        </template>

        <view class="divider" />
        <button class="btn btn--ghost" @tap="goDiagnosis">查看四维能力评估</button>
      </template>
    </view>

    <view class="safe-bottom" />
  </view>
</template>

<script setup>
/**
 * 作业中心：上传图片识别 → AI 批改。
 *
 * 两个动作都是异步任务（后端提交 job、客户端轮询），所以页面上有两处
 * 进度提示，而不是一个转圈的弹窗等到底。
 *
 * 图片一张一张传：后端接口收的是 files 数组，但 uni.uploadFile 的多文件
 * 参数只在微信小程序端可用，H5/App 不支持。逐张上传虽然慢一点，但同一份
 * 代码三端都能跑，而且能显示「第 2/3 张」的真实进度。
 */
import { computed, ref } from 'vue'

import { homeworkApi, pollJob } from '../../api'
import JobProgress from '../../components/job-progress.vue'
import CollapseItem from '../../components/collapse-item.vue'
import StatRow from '../../components/stat-row.vue'
import { upload } from '../../api/request'
import { catalogStore, ensureCatalog } from '../../store/catalog'
import { scoreClass } from '../../utils/format'

const text = ref('')
const images = ref([])
const fromImage = ref(false)
const recognizing = ref(false)
const recognizeIndex = ref(0)
const grading = ref(false)
const result = ref(null)

const errorTypes = computed(() => {
  const raw = (result.value && result.value.error_types) || {}
  return Object.keys(raw)
    .map((name) => ({ name, count: raw[name] }))
    .sort((a, b) => b.count - a.count)
})

ensureCatalog().catch(() => {})

function chooseImages() {
  uni.chooseImage({
    count: 5 - images.value.length,
    sizeType: ['compressed'],
    sourceType: ['camera', 'album'],
    success: (res) => {
      images.value = images.value.concat(res.tempFilePaths || []).slice(0, 5)
    },
  })
}

function preview(index) {
  uni.previewImage({ urls: images.value, current: images.value[index] })
}

function removeImage(index) {
  images.value.splice(index, 1)
}

function detailTitle(item) {
  if (item.is_right === true) return `第 ${item.index} 题｜✅ 正确`
  if (item.is_right === false) return `第 ${item.index} 题｜❌ ${item.error_type || '有误'}`
  return `第 ${item.index} 题｜❓ 待核对`
}

async function recognize() {
  if (!images.value.length) return
  recognizing.value = true
  const parts = []
  try {
    for (let index = 0; index < images.value.length; index++) {
      recognizeIndex.value = index + 1
      const { job_id } = await upload('/homework/recognize', images.value[index])
      const icon = await pollJob(job_id)
      const part = ((icon && icon.text) || '').trim()
      if (part) parts.push(part)
    }
    const merged = parts.join('\n\n')
    if (!merged) {
      uni.showToast({ title: '未识别到文字，请换更清晰的图片或手动输入', icon: 'none' })
      return
    }
    // 追加而不是覆盖：用户可能已经手动输入了一部分
    text.value = text.value.trim() ? `${text.value.trim()}\n\n${merged}` : merged
    fromImage.value = true
    uni.showToast({ title: '识别完成，请核对后提交批改', icon: 'none' })
  } catch (err) {
    uni.showToast({ title: err.message || '识别失败', icon: 'none' })
  } finally {
    recognizing.value = false
    recognizeIndex.value = 0
  }
}

async function grade() {
  if (text.value.trim().length < 10) {
    uni.showToast({ title: '内容太短了，请至少输入一个完整句子或一道题', icon: 'none' })
    return
  }
  grading.value = true
  result.value = null
  try {
    const { job_id } = await homeworkApi.grade(text.value.trim(), catalogStore.book, catalogStore.unit)
    result.value = await pollJob(job_id)
    uni.showToast({ title: '批改完成', icon: 'success' })
  } catch (err) {
    uni.showToast({ title: err.message || '批改失败', icon: 'none' })
  } finally {
    grading.value = false
  }
}

function goMembership() {
  uni.navigateTo({ url: '/pages/membership/membership' })
}

function goDiagnosis() {
  uni.navigateTo({ url: '/pages/diagnosis/diagnosis' })
}
</script>

<style scoped>
.warn {
  margin-top: 16rpx;
  padding: 16rpx 20rpx;
  border-radius: 12rpx;
  font-size: 24rpx;
  line-height: 1.6;
  background: #fdf3e3;
  color: #b7791f;
}

.warn--info {
  background: #eef4fd;
  color: #1d5ba8;
}

.ph {
  color: #c0c4cc;
}

.thumbs {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  margin-top: 20rpx;
}

.thumbs__item {
  position: relative;
  width: 160rpx;
  height: 160rpx;
  margin: 0 16rpx 16rpx 0;
  border-radius: 12rpx;
  overflow: hidden;
}

.thumbs__img {
  width: 160rpx;
  height: 160rpx;
}

.thumbs__del {
  position: absolute;
  top: 0;
  right: 0;
  width: 44rpx;
  height: 44rpx;
  line-height: 40rpx;
  text-align: center;
  background: rgba(0, 0, 0, 0.55);
  color: #ffffff;
  font-size: 30rpx;
  border-bottom-left-radius: 12rpx;
}

.thumbs__add {
  width: 160rpx;
  height: 160rpx;
  border: 2rpx dashed #c8ccd6;
  border-radius: 12rpx;
  color: #9ca3af;
  font-size: 52rpx;
  display: flex;
  align-items: center;
  justify-content: center;
}

.locked {
  display: flex;
  flex-direction: column;
}

.locked__title {
  font-size: 28rpx;
  font-weight: 600;
  color: #b7791f;
}

.locked__desc {
  font-size: 24rpx;
  color: #6b7280;
  margin-top: 8rpx;
  line-height: 1.6;
}

.comment {
  margin-top: 20rpx;
  font-size: 27rpx;
  color: #1f2937;
  line-height: 1.7;
}

.detail__line {
  display: block;
  font-size: 25rpx;
  color: #4b5563;
  line-height: 1.7;
  margin-bottom: 6rpx;
}

.detail__label {
  color: #9ca3af;
}

.errtype {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  font-size: 26rpx;
  color: #4b5563;
  padding: 12rpx 0;
}

.errtype__count {
  color: #dc2626;
}
</style>
