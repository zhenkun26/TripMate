import { describe, expect, it } from 'vitest'
import { formatDate, formatMonthDayTime } from './format'

describe('formatDate', () => {
  it('应把 YYYY-MM-DD 格式化为 M月D日', () => {
    expect(formatDate('2026-08-07')).toBe('8月7日')
    expect(formatDate('2026-12-31')).toBe('12月31日')
  })

  it('非法日期原样返回', () => {
    expect(formatDate('2026/08/07')).toBe('2026/08/07')
    expect(formatDate('')).toBe('')
  })
})

describe('formatMonthDayTime', () => {
  it('null 或空串返回 null', () => {
    expect(formatMonthDayTime(null)).toBeNull()
    expect(formatMonthDayTime('')).toBeNull()
  })

  it('非法时间返回 null', () => {
    expect(formatMonthDayTime('not-a-date')).toBeNull()
  })

  it('ISO 时间格式化为 M月D日 HH:mm', () => {
    expect(formatMonthDayTime('2026-08-07T08:05:00')).toBe('8月7日 08:05')
  })
})
