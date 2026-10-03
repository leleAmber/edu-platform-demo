/**
 * 教材目录：当前教材 + 当前单元。
 *
 * 对应网页版 components/book_selector.py —— 预习、复习、模拟卷都只围绕
 * 「当前教材的当前单元」展开，所以这份状态必须在页面之间共享并持久化。
 *
 * 单元选择存本地存储而不是每次重选：小程序冷启动后回到上次学的单元，
 * 比回到第一册第一单元更符合预期。
 */

import { reactive } from 'vue'

import { bookApi } from '../api'
import { getToken } from '../api/request'

const BOOK_KEY = 'keban_book'
const UNIT_KEY = 'keban_unit'

export const catalogStore = reactive({
  books: [],        // [{key, name, grade, units}]
  book: '',         // 当前教材 key，如「必修一」
  units: [],        // 当前教材的单元名列表
  unit: '',         // 当前单元
  loaded: false,
})

function readStorage(key) {
  try {
    return uni.getStorageSync(key) || ''
  } catch (e) {
    return ''
  }
}

function writeStorage(key, value) {
  try {
    uni.setStorageSync(key, value || '')
  } catch (e) {
    /* ignore */
  }
}

/** 教材列表只需拉一次。未登录直接跳过：冷启动时页面会先于登录跳转挂载，
 *  这时候发请求只会拿到 401，白白多三个来回。 */
export async function ensureCatalog() {
  if (catalogStore.loaded) return catalogStore
  if (!getToken()) return catalogStore

  const res = await bookApi.list()
  catalogStore.books = (res && res.books) || []

  const keys = catalogStore.books.map((b) => b.key)
  const saved = readStorage(BOOK_KEY)
  catalogStore.book = keys.indexOf(saved) >= 0 ? saved : keys[0] || ''

  catalogStore.loaded = true
  await syncUnits()
  return catalogStore
}

/** 按当前教材刷新单元列表，并保证 catalogStore.unit 落在列表内。 */
async function syncUnits() {
  if (!catalogStore.book) {
    catalogStore.units = []
    catalogStore.unit = ''
    return
  }

  const meta = catalogStore.books.find((b) => b.key === catalogStore.book)
  catalogStore.units = (meta && meta.units) || []

  if (!catalogStore.units.length) {
    // 目录里没带 units 的兜底：单独请求一次
    try {
      const res = await bookApi.units(catalogStore.book)
      catalogStore.units = (res && res.units) || []
    } catch (e) {
      catalogStore.units = []
    }
  }

  const saved = readStorage(UNIT_KEY)
  catalogStore.unit = catalogStore.units.indexOf(saved) >= 0
    ? saved
    : catalogStore.units[0] || ''
  writeStorage(UNIT_KEY, catalogStore.unit)
}

/** 切换教材：单元重置为新教材的首单元（跨书残留旧单元会取不到内容）。 */
export async function selectBook(book) {
  if (!book || book === catalogStore.book) return
  catalogStore.book = book
  catalogStore.unit = ''
  writeStorage(BOOK_KEY, book)
  await syncUnits()
}

/** 切换单元。 */
export function selectUnit(unit) {
  catalogStore.unit = unit || ''
  writeStorage(UNIT_KEY, catalogStore.unit)
}

/** 教材展示名：`必修一｜人教版必修第一册`。 */
export function bookLabel(key) {
  const meta = catalogStore.books.find((b) => b.key === key)
  return meta && meta.name ? `${key}｜${meta.name}` : key
}
