export interface ScannedAssetPayload {
  assetCode: string
  barcodeValue?: string
}

/**
 * Normalizes QR and barcode scan payloads.
 *
 * QR values use `/scan?asset_code=...&barcode=...` so the link remains usable
 * when the SPA is deployed under a sub-path.  Compound `code|barcode` values
 * are also accepted for scanners that do not follow links.  Legacy numeric
 * asset detail URLs are treated as asset codes so the SPA can still look up
 * the asset without exposing its internal ID.
 */
export function parseScannedAssetValue(rawValue: string): ScannedAssetPayload | null {
  const value = rawValue.trim()
  if (!value) return null

  if (value.startsWith('/') || /^https?:/i.test(value)) {
    try {
      const url = new URL(value, 'http://localhost')
      const compoundValue = url.searchParams.get('asset_code')?.trim()
      const compound = compoundValue ? parseScannedAssetValue(compoundValue) : null
      const assetCode = compound?.assetCode
      const barcode = url.searchParams.get('barcode')?.trim() || compound?.barcodeValue
      if (assetCode) {
        return barcode ? { assetCode, barcodeValue: barcode } : { assetCode }
      }

      const legacyMatch = url.pathname.match(/\/assets\/(?:code\/)?([^/]+)$/)
      if (legacyMatch?.[1]) {
        const assetCode = decodeURIComponent(legacyMatch[1]).trim()
        if (assetCode) {
          return barcode ? { assetCode, barcodeValue: barcode } : { assetCode }
        }
      }
      if (url.pathname.endsWith('/scan') || url.pathname.endsWith('/scan-use')) return null
    } catch {
      // Treat malformed URLs as plain scan text.
    }
  }

  if (value.includes('|')) {
    const [assetCode, barcode] = value.split('|')
    const normalizedCode = assetCode.trim()
    if (normalizedCode) {
      return { assetCode: normalizedCode, barcodeValue: barcode?.trim() || undefined }
    }
    return null
  }

  return { assetCode: value }
}
