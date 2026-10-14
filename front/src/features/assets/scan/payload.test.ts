import assert from 'node:assert/strict'
import test from 'node:test'
import { parseScannedAssetValue } from './payload.ts'

test('parses scan-to-use URL payloads', () => {
  assert.deepEqual(parseScannedAssetValue('/scan?asset_code=ZC-0001&barcode=SER-001'), {
    assetCode: 'ZC-0001',
    barcodeValue: 'SER-001',
  })
  assert.deepEqual(parseScannedAssetValue('https://example.com/scaffold/scan?asset_code=ZC-0001'), {
    assetCode: 'ZC-0001',
  })
  assert.deepEqual(
    parseScannedAssetValue(
      'https://example.com/scaffold/scan-use?asset_code=ZC-0001&barcode=SER-001',
    ),
    {
      assetCode: 'ZC-0001',
      barcodeValue: 'SER-001',
    },
  )
  assert.deepEqual(parseScannedAssetValue('/scan-use?asset_code=ZC-0001|SER-001'), {
    assetCode: 'ZC-0001',
    barcodeValue: 'SER-001',
  })
})

test('parses legacy URLs and ignores scan URLs without asset codes', () => {
  assert.deepEqual(parseScannedAssetValue('/assets/2'), { assetCode: '2' })
  assert.deepEqual(parseScannedAssetValue('/scan'), null)
  assert.deepEqual(parseScannedAssetValue('https://example.com/scaffold/assets/2'), {
    assetCode: '2',
  })
})

test('parses compound QR and plain barcode payloads', () => {
  assert.deepEqual(parseScannedAssetValue('ZC-0001|SER-001'), {
    assetCode: 'ZC-0001',
    barcodeValue: 'SER-001',
  })
  assert.deepEqual(parseScannedAssetValue(' ZC-0001 '), { assetCode: 'ZC-0001' })
})
