import { useEffect, useRef, useState } from 'react'
import html2canvas from 'html2canvas'
import QRCode from 'qrcode'
import type { KekeStory } from '@/types'

interface Props {
  story: KekeStory
  onClose: () => void
  onLongImageReady?: () => void
}

function buildShareUrl(): string {
  const base = import.meta.env.BASE_URL || '/'
  const normalised = base.endsWith('/') ? base : `${base}/`
  return `${window.location.origin}${normalised}keke/?from=share`
}

const SHARE_URL = buildShareUrl()

function blockClass(type: KekeStory['blocks'][number]['type']): string {
  if (type === 'question') return 'tpl-inter q'
  if (type === 'action') return 'tpl-inter a'
  return 'tpl-inter p'
}
function blockLabel(type: KekeStory['blocks'][number]['type']): string {
  if (type === 'question') return '💛 问问孩子'
  if (type === 'action') return '🙌 一起做动作'
  return '🔮 让孩子猜猜'
}

/**
 * Bottom-sheet share modal:
 * 1. Renders a hidden long-image template offscreen
 * 2. Generates QR code into the template's canvas slot
 * 3. Snapshots template with html2canvas → data URL → <img> preview
 *
 * The template lives inside this component (not the parent page) so it
 * unmounts cleanly when the user closes the modal.
 */
export default function ShareModal({ story, onClose, onLongImageReady }: Props) {
  const tplRef = useRef<HTMLDivElement | null>(null)
  const qrCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        if (qrCanvasRef.current) {
          await QRCode.toCanvas(qrCanvasRef.current, SHARE_URL, {
            width: 126,
            margin: 0,
            errorCorrectionLevel: 'M',
          })
        }
        // Let layout settle before snapshotting
        await new Promise((r) => setTimeout(r, 100))
        if (!tplRef.current || cancelled) return
        const canvas = await html2canvas(tplRef.current, {
          scale: 2,
          useCORS: true,
          backgroundColor: '#FFF4E6',
          logging: false,
        })
        if (cancelled) return
        setPreview(canvas.toDataURL('image/png'))
        onLongImageReady?.()
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : '生成失败')
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [story, onLongImageReady])

  return (
    <div className="share-modal">
      <button className="share-close" type="button" onClick={onClose}>
        ×
      </button>
      <div className="share-preview">
        {preview ? (
          <img src={preview} alt="故事长图" />
        ) : error ? (
          <div className="share-placeholder">
            长图生成失败 😿
            <br />
            <span style={{ fontSize: 12, opacity: 0.7 }}>{error}</span>
          </div>
        ) : (
          <div className="share-placeholder">正在生成长图…</div>
        )}
      </div>
      <div className="share-tip">
        长按上方图片即可保存到相册
        <br />
        分享给更多家长，一起听故事 🌙
      </div>
      <button className="share-save-btn" type="button" onClick={onClose}>
        完成
      </button>

      {/* Hidden long-image template — html2canvas snapshots this */}
      <div className="share-canvas-tpl" ref={tplRef}>
        <div className="tpl-hero">
          <div className="tpl-brand">帆书APP · 波波龟工作室出品</div>
          <div className="tpl-title">{story.title}</div>
          <div className="tpl-kw">🌟 今晚的故事：{story.keyword}</div>
        </div>
        <div className="tpl-body">
          {story.blocks.map((b, i) =>
            b.type === 'para' ? (
              <div key={i} className="tpl-para">
                {b.text}
              </div>
            ) : (
              <div key={i} className={blockClass(b.type)}>
                <div className="tpl-inter-tag">{blockLabel(b.type)}</div>
                {b.text}
              </div>
            ),
          )}
        </div>
        <div className="tpl-footer">
          <div className="tpl-footer-text">
            <div className="tpl-footer-title">呼噜与可可的欢乐时光</div>
            <div className="tpl-footer-sub">
              扫码生成专属于你孩子的
              <br />
              睡前故事脚本
            </div>
          </div>
          <div className="tpl-qr">
            <canvas ref={qrCanvasRef} />
          </div>
        </div>
      </div>
    </div>
  )
}
