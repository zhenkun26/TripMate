/**
 * 展示格式化工具。
 */

/** 把 ISO 时间解析为 M月D日 HH:mm；解析失败返回 null。 */
export function formatMonthDayTime(isoValue: string | null): string | null {
  if (!isoValue) {
    return null
  }
  const parsed = new Date(isoValue)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }
  const month = parsed.getMonth() + 1
  const day = parsed.getDate()
  const hours = String(parsed.getHours()).padStart(2, '0')
  const minutes = String(parsed.getMinutes()).padStart(2, '0')
  return `${month}月${day}日 ${hours}:${minutes}`
}

/** 解析 YYYY-MM-DD 为 M月D日；解析失败返回原始字符串。 */
export function formatDate(dateValue: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue)
  if (!match) {
    return dateValue
  }
  return `${Number(match[2])}月${Number(match[3])}日`
}
