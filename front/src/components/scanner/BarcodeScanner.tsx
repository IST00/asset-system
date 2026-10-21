import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Input, Modal, Typography } from 'antd'
import { Camera, ScanLine } from 'lucide-react'
import { parseScannedAssetValue } from '@/features/assets/scan/payload'
import type { AssetScanPurpose } from '@/features/assets/scan/scanIntentModel'
import { BrowserMultiFormatReader } from '@zxing/browser'

interface BarcodeResultLike {
  rawValue: string
}

interface BarcodeDetectorLike {
  detect(source: HTMLVideoElement): Promise<BarcodeResultLike[]>
}

interface BarcodeDetectorConstructorLike {
  new (options?: { formats?: string[] }): BarcodeDetectorLike
}

interface BrowserWithBarcodeDetector extends Window {
  BarcodeDetector?: BarcodeDetectorConstructorLike
}

interface BarcodeScannerProps {
  open: boolean
  title?: string
  onClose: () => void
  onDetected: (value: string) => void
  loading?: boolean
  scanToUse?: boolean
  preferredPurpose?: AssetScanPurpose
}

export default function BarcodeScanner({
  open,
  title = '扫码识别资产',
  onClose,
  onDetected,
  loading = false,
  scanToUse = false,
  preferredPurpose,
}: BarcodeScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const intervalRef = useRef<number | null>(null)
  const [scannerError, setScannerError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [manualCode, setManualCode] = useState('')
  const [manualError, setManualError] = useState<string | null>(null)
  const [decodeError, setDecodeError] = useState<string | null>(null)

  const buildScanUseUrl = useCallback(
    (scanned: { assetCode: string; barcodeValue?: string; handoverToken?: string }) => {
      const baseUrl = import.meta.env.BASE_URL
      const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
      if (scanned.handoverToken) {
        return `${base}asset-transfer?handover_token=${encodeURIComponent(scanned.handoverToken)}`
      }
      const params = new URLSearchParams()
      if (scanned.assetCode) params.set('asset_code', scanned.assetCode)
      if (scanned.barcodeValue) params.set('barcode', scanned.barcodeValue)
      if (preferredPurpose) params.set('preferred', preferredPurpose)
      return `${base}scan-use?${params.toString()}`
    },
    [preferredPurpose],
  )

  const handleDetectedValue = (value: string) => {
    const scanned = parseScannedAssetValue(value)
    if (!scanned) {
      setDecodeError('已识别到内容，但不是有效资产二维码或编码。')
      return
    }
    stop()
    if (scanToUse) {
      window.location.href = buildScanUseUrl(scanned)
      return
    }
    onDetected(value)
  }

  const stop = useCallback(() => {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current)
    intervalRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setRunning(false)
  }, [])

  useEffect(() => {
    if (!open) stop()
    return stop
  }, [open, stop])

  const start = async () => {
    setScannerError(null)
    const Detector = (window as BrowserWithBarcodeDetector).BarcodeDetector
    if (!Detector) {
      setScannerError('当前浏览器不支持原生条码识别，将使用通用解码器。')
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      })
      streamRef.current = stream
      const video = videoRef.current
      if (!video) return
      video.srcObject = stream
      await video.play()
      setRunning(true)
      const detector = Detector
        ? new Detector({ formats: ['qr_code', 'code_128', 'code_39'] })
        : null
      const fallbackReader = new BrowserMultiFormatReader()
      intervalRef.current = window.setInterval(() => {
        if (loading || video.readyState < video.HAVE_CURRENT_DATA) return
        void (detector ? detector.detect(video) : Promise.resolve<BarcodeResultLike[]>([]))
          .catch(async () => {
            // Some embedded browsers expose BarcodeDetector but cannot decode it.
            const result = await fallbackReader.decodeOnceFromVideoElement(video)
            return [{ rawValue: result.getText() }]
          })
          .then(async (results) => {
            const value = results[0]?.rawValue
            if (value) return results
            // Also use the portable decoder when the native API returns nothing.
            const result = await fallbackReader.decodeOnceFromVideoElement(video)
            return [{ rawValue: result.getText() }]
          })
          .then((results) => {
            const value = results[0]?.rawValue
            if (!value) return
            setDecodeError(null)
            handleDetectedValue(value)
          })
          .catch((error: unknown) => {
            setDecodeError(
              error instanceof Error && error.message
                ? `摄像头画面识别失败：${error.message}`
                : null,
            )
          })
      }, 550)
    } catch (error) {
      setScannerError(error instanceof Error ? error.message : '无法启用摄像头')
      stop()
    }
  }

  const submitManualCode = () => {
    const value = manualCode.trim()
    if (!value) {
      setManualError('请输入资产二维码内容、条形码或资产编码')
      return
    }
    const scanned = parseScannedAssetValue(value)
    if (!scanned) {
      setManualError('无法识别资产编码，请重新扫码或输入')
      return
    }
    setManualError(null)
    if (scanToUse) {
      stop()
      window.location.href = buildScanUseUrl(scanned)
      return
    }
    onDetected(value)
  }

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} destroyOnHidden>
      <div className="inventory-scanner">
        <video ref={videoRef} muted playsInline className={running ? 'is-running' : ''} />
        {!running ? (
          <div className="inventory-scanner__placeholder">
            <ScanLine size={38} />
            <strong>扫描资产二维码或条形码</strong>
            <span>识别成功后自动进入领用 / 借用办理。</span>
          </div>
        ) : null}
        {scannerError ? <Alert type="warning" showIcon message={scannerError} /> : null}
        {decodeError ? (
          <Alert
            type="info"
            showIcon
            message={decodeError}
            description="请保持二维码完整、无反光，距离标签 10-25 厘米；若仍无法识别，可使用下方手动输入。"
          />
        ) : null}
        <Typography.Text type="secondary">
          支持二维码、Code 39、Code 128；内置浏览器不支持摄像头识别时可手动提交。
        </Typography.Text>
        <Button
          type="primary"
          size="large"
          icon={<Camera size={18} />}
          onClick={running ? stop : () => void start()}
          loading={loading}
          block
        >
          {running ? '停止扫描' : '打开摄像头'}
        </Button>
        <div className="inventory-scanner__manual">
          <Input.Search
            value={manualCode}
            onChange={(event) => {
              setManualCode(event.target.value)
              setManualError(null)
            }}
            onSearch={submitManualCode}
            placeholder="浏览器不支持扫码时，请输入资产编码或条码内容"
            enterButton="手动提交"
            disabled={loading}
          />
          {manualError ? <Alert type="error" showIcon message={manualError} /> : null}
        </div>
      </div>
    </Modal>
  )
}
