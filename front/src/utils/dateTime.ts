const API_OFFSET = /(Z|[+-]\d{2}:\d{2})$/i

const beijingFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

export function parseUtcInstant(value: string): Date {
  const normalized = API_OFFSET.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) throw new Error('Invalid API datetime')
  return date
}

function beijingParts(value: string): Record<string, string> {
  return Object.fromEntries(
    beijingFormatter.formatToParts(parseUtcInstant(value)).map((part) => [part.type, part.value]),
  )
}

export function formatBeijingDateTime(value: string): string {
  try {
    const part = beijingParts(value)
    return `${part.year}-${part.month}-${part.day} ${part.hour}:${part.minute}:${part.second}`
  } catch {
    return value
  }
}

export function beijingDateKey(value: string): string {
  const part = beijingParts(value)
  return `${part.year}-${part.month}-${part.day}`
}
