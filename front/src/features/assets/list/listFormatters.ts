interface IntlRuntime {
  readonly DateTimeFormat: typeof Intl.DateTimeFormat
  readonly NumberFormat: typeof Intl.NumberFormat
}

function getIntlRuntime(): IntlRuntime | null {
  if (
    typeof Intl === 'undefined' ||
    typeof Intl.DateTimeFormat !== 'function' ||
    typeof Intl.NumberFormat !== 'function'
  ) {
    return null
  }

  return {
    DateTimeFormat: Intl.DateTimeFormat,
    NumberFormat: Intl.NumberFormat,
  }
}

function parseLocalDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(year, month - 1, day)

  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null
  }

  return date
}

function formatAmountFallback(value: number): string {
  if (value !== value || value === Infinity || value === -Infinity) return String(value)

  const sign = value < 0 ? '-' : ''
  const parts = Math.abs(value).toFixed(2).split('.')
  const integer = (parts[0] ?? '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${sign}¥${integer}.${parts[1] ?? '00'}`
}

export function formatAssetDate(
  value: string,
  locale: string,
  intlRuntime: IntlRuntime | null = getIntlRuntime(),
): string {
  const date = parseLocalDate(value)
  if (!date || !intlRuntime) return value

  try {
    return new intlRuntime.DateTimeFormat(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(date)
  } catch {
    return value
  }
}

export function formatAssetAmount(
  value: number,
  locale: string,
  intlRuntime: IntlRuntime | null = getIntlRuntime(),
): string {
  if (!intlRuntime) return formatAmountFallback(value)

  try {
    return new intlRuntime.NumberFormat(locale, {
      style: 'currency',
      currency: 'CNY',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  } catch {
    return formatAmountFallback(value)
  }
}
