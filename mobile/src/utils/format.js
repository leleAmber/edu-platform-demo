/**
 * 展示层的小工具。集中放这里，避免每个页面各写一份。
 */

/** 评级 → 标签类型。与 core/tutor_ai.level_tag_type 的映射保持一致。 */
export function levelChip(level) {
  if (level === '优秀') return 'success'
  if (level === '良好') return 'warning'
  return 'danger'
}

/** 分数 → 颜色 class。 */
export function scoreClass(score) {
  const value = Number(score) || 0
  if (value >= 85) return 'text-success'
  if (value >= 70) return 'text-warning'
  return 'text-danger'
}

/**
 * 把选项原文转成 A/B/C/D 字母。
 *
 * 后端的答案存的是选项原文（如 "sign up"），而手机上选项前缀是字母，
 * 批改结果里显示原文太长，转成字母更好读。找不到时原样返回。
 */
export function optionLetter(options, text) {
  if (!text) return ''
  const index = (options || []).indexOf(text)
  return index >= 0 ? String.fromCharCode(65 + index) : text
}

/** 截断长文本。 */
export function truncate(text, max = 30) {
  const value = String(text || '')
  return value.length > max ? `${value.slice(0, max)}…` : value
}

/** 秒 → 「1 分 20 秒」。 */
export function formatDuration(seconds) {
  const value = Math.max(0, Math.floor(seconds || 0))
  if (value < 60) return `${value} 秒`
  return `${Math.floor(value / 60)} 分 ${value % 60} 秒`
}

/**
 * 把教材内容里的 words 归一化成列表项。
 * 真实教材的 words 元素是 {word, pos, explain}，内置演示内容还多一个 sentence。
 */
export function normalizeWords(words) {
  return (words || []).map((item, index) => ({
    index: index + 1,
    word: item.word || '',
    pos: item.pos || '',
    explain: item.explain || '',
    sentence: item.sentence || '',
  }))
}

/** 归一化练习题：题库来源少字段，统一补齐，页面就不必到处判空。 */
export function normalizeQuestions(questions) {
  return (questions || []).map((item, index) => ({
    index,
    id: item.id || `q${index}`,
    question: item.question || '',
    options: item.options || [],
    answer: item.answer || '',
    explain: item.explain || '',
  }))
}
