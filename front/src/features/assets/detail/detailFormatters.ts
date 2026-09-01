const purchaseDatePattern = /^(\d{4})-(\d{2})-(\d{2})$/

function createPurchaseDate(value: string): Date | null {
  const match = purchaseDatePattern.exec(value)
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

function canFormatDates(): boolean {
  return typeof Intl !== 'undefined' && typeof Intl.DateTimeFormat === 'function'
}

function canFormatNumbers(): boolean {
  return typeof Intl !== 'undefined' && typeof Intl.NumberFormat === 'function'
}

export function formatAssetDate(value: string, locale: string): string {
  const date = createPurchaseDate(value)
  if (!date || !canFormatDates()) return value

  try {
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(date)
  } catch {
    return value
  }
}

export function formatAssetAmount(value: number, locale: string): string {
  if (canFormatNumbers()) {
    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: 'CNY',
        minimumFractionDigits: 2,
      }).format(value)
    } catch {
      // Fall through to the fixed-format value for legacy or incomplete Intl implementations.
    }
  }

  return `¥${value.toFixed(2)}`
}
