/**
 * 接口清单。
 *
 * 与后端 app/routers/ 一一对应，改接口时两边一起改。
 * 批改类接口是异步的：先拿到 job_id，再轮询 /jobs/{id} 取结果。
 */

import { POLL_INTERVAL, POLL_MAX_TRIES } from '../config'
import { request, upload } from './request'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// --------------------------------------------------------------------------- #
// 认证
// --------------------------------------------------------------------------- #
export const authApi = {
  sendCode: (email) => request({ url: '/auth/send-code', method: 'POST', data: { email } }),

  register: (payload) => request({ url: '/auth/register', method: 'POST', data: payload }),

  login: (username, password) =>
    request({ url: '/auth/login', method: 'POST', data: { username, password } }),

  wechatLogin: (code) => request({ url: '/auth/wechat', method: 'POST', data: { code } }),

  me: () => request({ url: '/auth/me' }),

  logout: () => request({ url: '/auth/logout', method: 'POST' }),
}

// --------------------------------------------------------------------------- #
// 教材
// --------------------------------------------------------------------------- #
export const bookApi = {
  list: () => request({ url: '/textbooks' }),

  units: (book) => request({ url: `/textbooks/${encodeURIComponent(book)}/units` }),

  unitContent: (book, unit) =>
    request({
      url: `/textbooks/${encodeURIComponent(book)}/units/${encodeURIComponent(unit)}`,
    }),

  refreshQuiz: (book, unit, quizType) =>
    request({
      url: `/textbooks/${encodeURIComponent(book)}/units/${encodeURIComponent(unit)}/refresh-quiz`,
      data: { quiz_type: quizType },
    }),
}

// --------------------------------------------------------------------------- #
// 预习 / 复习
// --------------------------------------------------------------------------- #
export const learnApi = {
  gradeQuiz: (book, unit, quizType, answers) =>
    request({ url: '/quiz/grade', method: 'POST', data: { book, unit, quiz_type: quizType, answers } }),

  studyPlan: (planType, book, unit) =>
    request({ url: '/study-plan', method: 'POST', data: { plan_type: planType, book, unit } }),

  records: (limit = 20) => request({ url: '/records', data: { limit } }),
}

// --------------------------------------------------------------------------- #
// 作业
// --------------------------------------------------------------------------- #
export const homeworkApi = {
  /** 单张图片识别：上传 → 拿 job_id → 轮询到出文字。 */
  recognizeOne: async (filePath, onProgress) => {
    const { job_id } = await upload('/homework/recognize', filePath)
    return pollJob(job_id, onProgress)
  },

  grade: (text, book, unit) =>
    request({ url: '/homework/grade', method: 'POST', data: { text, book, unit } }),
}

// --------------------------------------------------------------------------- #
// 模拟试卷
// --------------------------------------------------------------------------- #
export const examApi = {
  get: (book, refresh = false) => request({ url: '/mock-exam', data: { book, refresh } }),

  grade: (book, answers, writings) =>
    request({ url: '/mock-exam/grade', method: 'POST', data: { book, answers, writings } }),
}

// --------------------------------------------------------------------------- #
// 学情 / 会员 / 留言
// --------------------------------------------------------------------------- #
export const diagnosisApi = {
  get: () => request({ url: '/diagnosis' }),
}

export const membershipApi = {
  plans: () => request({ url: '/membership/plans' }),
  purchase: (plan) => request({ url: '/membership/purchase', method: 'POST', data: { plan } }),
  orders: () => request({ url: '/membership/orders' }),
}

export const messageApi = {
  list: () => request({ url: '/messages' }),
  create: (content) => request({ url: '/messages', method: 'POST', data: { content } }),
}

// --------------------------------------------------------------------------- #
// 异步任务
// --------------------------------------------------------------------------- #
/**
 * 轮询任务直到完成。
 *
 * 后端把耗时的大模型调用放进了后台任务，接口本身很快返回——这样既避开了
 * 微信云托管 callContainer 的 15 秒硬限制，也让手机端能显示真实进度而不是干等。
 *
 * @param {string} jobId
 * @param {(attempt:number)=>void} [onProgress] 每次轮询回调，用于更新「已等待 N 秒」
 * @returns {Promise<any>} 任务结果
 */
export async function pollJob(jobId, onProgress) {
  for (let attempt = 0; attempt < POLL_MAX_TRIES; attempt++) {
    if (onProgress) onProgress(attempt)

    let job
    try {
      job = await request({ url: `/jobs/${jobId}` })
    } catch (err) {
      // 网络抖动不该让整个任务失败，继续重试
      if (err.status === 404) throw new Error('任务不存在或已过期，请重新提交')
      if (err.status === 401) throw err
      await sleep(POLL_INTERVAL)
      continue
    }

    if (job.status === 'done') return job.result
    if (job.status === 'error') throw new Error(job.error || '处理失败，请稍后重试')

    await sleep(job.poll_interval ? job.poll_interval * 1000 : POLL_INTERVAL)
  }
  throw new Error('处理超时，请稍后重试')
}
