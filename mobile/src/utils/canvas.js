/**
 * canvas 小工具。
 *
 * 小程序与 H5 的 canvas API 与网页版完全不同（网页版用 plotly，这里是
 * 原生 canvas 2d），所以两个图表（雷达图、柱状图）都得手绘。
 */

import { getCurrentInstance, onMounted, watch } from 'vue'

let seq = 0

/**
 * 生成组件内唯一的 canvas-id。
 *
 * 小程序里 canvas-id 是全局命名空间，同页面出现两个图表时必须唯一，
 * 否则后画的会覆盖先画的。
 */
export function useCanvasId(prefix) {
  seq += 1
  return `${prefix}-${seq}`
}

/** 在组件内查询节点尺寸（px）。画布坐标系用的就是 px，不是 rpx。 */
export function queryRect(selector, instance) {
  return new Promise((resolve) => {
    const query = uni.createSelectorQuery()
    if (instance) query.in(instance)
    query
      .select(selector)
      .boundingClientRect((rect) => resolve(rect || null))
      .exec()
  })
}

/**
 * 画布就绪后执行绘制。
 *
 * onMounted 那一刻节点可能还没布局完，boundingClientRect 会返回 0，
 * 所以这里等到拿到有效宽高再画；尺寸拿不到就退到系统窗口宽度兜底，
 * 宁可画得略微不准也不要整块空白。
 */
export function useCanvasDraw(canvasId, draw) {
  const instance = getCurrentInstance() ? getCurrentInstance().proxy : null

  async function run() {
    let rect = await queryRect(`#${canvasId}`, instance)
    if (!rect || !rect.width || !rect.height) {
      // 再等一帧重试一次
      await new Promise((resolve) => setTimeout(resolve, 120))
      rect = await queryRect(`#${canvasId}`, instance)
    }
    if (!rect || !rect.width || !rect.height) {
      const info = uni.getSystemInfoSync()
      rect = { width: info.windowWidth - 48, height: 300 }
    }
    const ctx = uni.createCanvasContext(canvasId, instance)
    draw(ctx, rect.width, rect.height)
    ctx.draw()
  }

  onMounted(run)
  return run
}

/** 折线/多边形路径。 */
export function polygon(ctx, points) {
  points.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y)
    else ctx.lineTo(point.x, point.y)
  })
  ctx.closePath()
}
