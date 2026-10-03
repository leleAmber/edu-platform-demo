<template>
  <view class="chart">
    <canvas :canvas-id="canvasId" :id="canvasId" class="chart__canvas" />
  </view>
</template>

<script setup>
/**
 * 四维能力雷达图。
 *
 * 网页版用 plotly，小程序里换成原生 canvas 手绘：4 条轴（词汇/句法/语篇/写作）、
 * 25/50/75/100 四圈参考网格，另外用虚线画出 85 分的「优秀线」，
 * 让学生一眼看出自己离优秀还差多少。
 */
import { watch } from 'vue'

import { polygon, useCanvasDraw, useCanvasId } from '../utils/canvas'

const props = defineProps({
  categories: { type: Array, default: () => [] },
  values: { type: Array, default: () => [] },
  max: { type: Number, default: 100 },
  excellentLine: { type: Number, default: 85 },
})

const canvasId = useCanvasId('radar')

function render(ctx, width, height) {
  const categories = props.categories || []
  const values = props.values || []
  const count = categories.length
  if (!count) return

  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) / 2 - 44

  ctx.clearRect(0, 0, width, height)

  const angleAt = (index) => -Math.PI / 2 + (index * 2 * Math.PI) / count
  const pointAt = (index, ratio) => ({
    x: cx + radius * ratio * Math.cos(angleAt(index)),
    y: cy + radius * ratio * Math.sin(angleAt(index)),
  })

  // 参考网格
  ;[0.25, 0.5, 0.75, 1].forEach((ratio) => {
    ctx.beginPath()
    polygon(ctx, categories.map((_, index) => pointAt(index, ratio)))
    ctx.setStrokeStyle('#e5e8ef')
    ctx.setLineWidth(1)
    ctx.stroke()
  })

  // 轴线
  categories.forEach((_, index) => {
    const outer = pointAt(index, 1)
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.lineTo(outer.x, outer.y)
    ctx.setStrokeStyle('#e5e8ef')
    ctx.setLineWidth(1)
    ctx.stroke()
  })

  // 优秀线（85 分）
  const excellentRatio = Math.min(1, props.excellentLine / props.max)
  ctx.beginPath()
  polygon(ctx, categories.map((_, index) => pointAt(index, excellentRatio)))
  ctx.setStrokeStyle('#f0b429')
  ctx.setLineWidth(1)
  ctx.stroke()

  // 数据多边形
  const dataPoints = values.map((value, index) =>
    pointAt(index, Math.max(0, Math.min(1, (Number(value) || 0) / props.max)))
  )
  ctx.beginPath()
  polygon(ctx, dataPoints)
  ctx.setFillStyle('rgba(42, 120, 214, 0.22)')
  ctx.fill()
  ctx.setStrokeStyle('#2a78d6')
  ctx.setLineWidth(2)
  ctx.stroke()

  // 顶点圆点
  dataPoints.forEach((point) => {
    ctx.beginPath()
    ctx.arc(point.x, point.y, 4, 0, Math.PI * 2)
    ctx.setFillStyle('#2a78d6')
    ctx.fill()
  })

  // 维度名 + 分值
  ctx.setFontSize(11)
  categories.forEach((name, index) => {
    const outer = pointAt(index, 1)
    const angle = angleAt(index)
    const labelX = cx + (radius + 26) * Math.cos(angle)
    const labelY = cy + (radius + 22) * Math.sin(angle)
    const value = Number(values[index]) || 0

    ctx.setTextAlign(Math.abs(Math.cos(angle)) < 0.2 ? 'center' : Math.cos(angle) > 0 ? 'left' : 'right')
    ctx.setTextBaseline('middle')
    ctx.setFillStyle('#6b7280')
    ctx.fillText(name, labelX, labelY - 7)
    ctx.setFillStyle('#1f2937')
    ctx.fillText(String(value), labelX, labelY + 8)
  })
}

const redraw = useCanvasDraw(canvasId, render)

watch(() => [props.values, props.categories], redraw, { deep: true })
</script>

<style scoped>
.chart {
  width: 100%;
  height: 460rpx;
}

.chart__canvas {
  width: 100%;
  height: 460rpx;
}
</style>
