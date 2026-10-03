<template>
  <view class="chart">
    <canvas :canvas-id="canvasId" :id="canvasId" class="chart__canvas" />
  </view>
</template>

<script setup>
/**
 * 学习进度柱状图（最近 8 次练习得分）。
 *
 * 同样替代了网页版的 plotly 图。85 分优秀线用虚线横贯全图，
 * 柱子按分数区间着色，扫一眼就能看出哪次掉下来了。
 */
import { watch } from 'vue'

import { useCanvasDraw, useCanvasId } from '../utils/canvas'

const props = defineProps({
  labels: { type: Array, default: () => [] },
  values: { type: Array, default: () => [] },
  max: { type: Number, default: 100 },
  excellentLine: { type: Number, default: 85 },
})

const canvasId = useCanvasId('bar')

function barColor(value) {
  if (value >= 85) return '#1f9d55'
  if (value >= 70) return '#2a78d6'
  return '#e08a3c'
}

function render(ctx, width, height) {
  const labels = props.labels || []
  const values = props.values || []
  const count = values.length
  if (!count) return

  const paddingLeft = 34
  const paddingRight = 12
  const paddingTop = 16
  const paddingBottom = 40
  const plotWidth = width - paddingLeft - paddingRight
  const plotHeight = height - paddingTop - paddingBottom

  ctx.clearRect(0, 0, width, height)

  const toY = (value) => paddingTop + plotHeight * (1 - Math.min(1, value / props.max))

  // 横向参考线：0 / 50 / 100
  ctx.setFontSize(10)
  ctx.setTextAlign('right')
  ctx.setTextBaseline('middle')
  ;[0, 50, 100].forEach((tick) => {
    const y = toY(tick)
    ctx.beginPath()
    ctx.moveTo(paddingLeft, y)
    ctx.lineTo(width - paddingRight, y)
    ctx.setStrokeStyle('#eef0f5')
    ctx.setLineWidth(1)
    ctx.stroke()
    ctx.setFillStyle('#9ca3af')
    ctx.fillText(String(tick), paddingLeft - 8, y)
  })

  // 优秀线
  const excellentY = toY(props.excellentLine)
  ctx.beginPath()
  ctx.moveTo(paddingLeft, excellentY)
  ctx.lineTo(width - paddingRight, excellentY)
  ctx.setStrokeStyle('#f0b429')
  ctx.setLineWidth(1)
  ctx.stroke()

  // 柱体
  const slot = plotWidth / count
  const barWidth = Math.max(10, Math.min(28, slot * 0.55))

  values.forEach((raw, index) => {
    const value = Number(raw) || 0
    const centerX = paddingLeft + slot * index + slot / 2
    const barHeight = Math.max(2, plotHeight * Math.min(1, value / props.max))
    const x = centerX - barWidth / 2
    const y = paddingTop + plotHeight - barHeight

    ctx.beginPath()
    ctx.setFillStyle(barColor(value))
    ctx.fillRect(x, y, barWidth, barHeight)

    // 柱顶分值
    ctx.setFontSize(10)
    ctx.setTextAlign('center')
    ctx.setTextBaseline('bottom')
    ctx.setFillStyle('#6b7280')
    ctx.fillText(String(value), centerX, y - 3)

    // 底部标签（模块名较长时截断）
    ctx.setTextBaseline('top')
    ctx.setFillStyle('#9ca3af')
    const label = String(labels[index] || '')
    ctx.fillText(label.length > 4 ? `${label.slice(0, 4)}…` : label, centerX, paddingTop + plotHeight + 8)
  })
}

const redraw = useCanvasDraw(canvasId, render)

watch(() => [props.values, props.labels], redraw, { deep: true })
</script>

<style scoped>
.chart {
  width: 100%;
  height: 400rpx;
}

.chart__canvas {
  width: 100%;
  height: 400rpx;
}
</style>
