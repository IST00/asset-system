import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { kekeApi } from '@/api'
import { useKekeStore } from '@/store/keke'
import type { KekeStory, KekeStoryBlock } from '@/types'
import { kekeAsset } from '@/utils/keke/asset'
import { detectUA, getDeviceId, getFromTag } from '@/utils/keke/device'
import { saveToHistory } from '@/utils/keke/history'
import { parseStory } from '@/utils/keke/story'
import { checkAndIncrementUsage, getRemaining, refundUsage } from '@/utils/keke/usage'
import { useTrackEvent } from './hooks/useTrackVisit'
import ShareModal from './ShareModal'

const KW_SUGGEST = [
  '下雨天',
  '冰激凌',
  '打针',
  '星星',
  '新朋友',
  '搭积木',
  '迷路了',
  '分享',
  '睡不着',
  '气球',
] as const

function pickFive<T>(list: readonly T[]): T[] {
  return [...list].sort(() => Math.random() - 0.5).slice(0, 5)
}

function StoryBlocks({ blocks }: { blocks: KekeStoryBlock[] }) {
  const [show, setShow] = useState(0)
  useEffect(() => {
    setShow(0)
    const timers: number[] = []
    for (let i = 0; i < blocks.length; i++) {
      timers.push(window.setTimeout(() => setShow((n) => Math.max(n, i + 1)), i * 90))
    }
    return () => timers.forEach(window.clearTimeout)
  }, [blocks])

  return (
    <>
      {blocks.map((b, i) => {
        const shown = i < show
        const klass = shown ? 'script-block show' : 'script-block'
        if (b.type === 'para') {
          return (
            <div key={i} className={klass}>
              <div className="story-para">{b.text}</div>
            </div>
          )
        }
        const cfg =
          b.type === 'question'
            ? { box: 'block-question', label: '💛 问问孩子' }
            : b.type === 'action'
              ? { box: 'block-action', label: '🙌 一起做动作' }
              : { box: 'block-predict', label: '🔮 让孩子猜猜' }
        return (
          <div key={i} className={klass}>
            <div className={cfg.box}>
              <div className="block-tag">{cfg.label}</div>
              <div className="block-text">{b.text}</div>
            </div>
          </div>
        )
      })}
    </>
  )
}

export default function Story() {
  const navigate = useNavigate()
  const track = useTrackEvent()
  const currentStory = useKekeStore((s) => s.currentStory)
  const setCurrentStory = useKekeStore((s) => s.setCurrentStory)

  const [keyword, setKeyword] = useState('')
  const [chips, setChips] = useState<string[]>(() => pickFive(KW_SUGGEST))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [shareOpen, setShareOpen] = useState(false)
  const [remaining, setRemaining] = useState(getRemaining())

  const story = currentStory
  const view: 'input' | 'loading' | 'story' = loading ? 'loading' : story ? 'story' : 'input'

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 2800)
  }, [])

  const resetToInput = useCallback(() => {
    setKeyword('')
    setError(null)
    setCurrentStory(null)
    setChips(pickFive(KW_SUGGEST))
    setRemaining(getRemaining())
    window.scrollTo(0, 0)
  }, [setCurrentStory])

  const generate = useCallback(async () => {
    const kw = keyword.trim()
    if (!kw) {
      showToast('说个关键词吧，比如：下雨天 😊')
      return
    }
    if (getRemaining() <= 0) {
      showToast('今天的故事次数用完了，明天再来吧 🌙')
      return
    }
    checkAndIncrementUsage()
    setRemaining(getRemaining())
    setLoading(true)
    setError(null)

    const t0 = Date.now()
    try {
      const res = await kekeApi.generateStory({
        device_id: getDeviceId(),
        from: getFromTag(),
        ua: detectUA(),
        keyword: kw,
      })
      const parsed: KekeStory = parseStory(res.content, kw)
      setCurrentStory(parsed)
      saveToHistory(parsed)
      track('generate_success', { keyword: kw, duration_ms: Date.now() - t0 })
    } catch (e) {
      refundUsage()
      setRemaining(getRemaining())
      setError(e instanceof Error ? e.message : '生成失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [keyword, setCurrentStory, showToast, track])

  const openShare = useCallback(() => {
    if (!story) {
      showToast('还没有故事可以分享哦')
      return
    }
    track('save_open', { keyword: story.keyword })
    setShareOpen(true)
  }, [story, showToast, track])

  const onLongImageReady = useCallback(() => {
    if (story) track('save_success', { keyword: story.keyword })
  }, [story, track])

  const remainingText = useMemo(
    () =>
      remaining > 0 ? `今天还能生成 ${remaining} 个故事` : '今天的故事次数用完啦，明天再来吧 🌙',
    [remaining],
  )

  return (
    <div className="page-story">
      <div className="story-header">
        <button className="back-btn" type="button" onClick={() => navigate('/keke/home')}>
          ←
        </button>
        <div className="story-header-info">
          <div className="story-header-title">{story ? story.title : '今晚的故事'}</div>
          <div className="story-header-sub">家长朗读脚本 · 波波动物城</div>
        </div>
        <button className="story-new-btn" type="button" onClick={resetToInput}>
          换一个 ↩
        </button>
      </div>

      {view === 'input' && (
        <div className="keyword-section">
          <div className="kw-label">今晚，你想听什么故事？</div>
          <div className="kw-sublabel">让孩子说一个词，故事就从这里长出来</div>
          <input
            className="kw-input"
            type="text"
            placeholder="比如：下雨天、冰激凌、打针、星星……"
            maxLength={20}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <div className="kw-chips">
            {chips.map((c) => (
              <div key={c} className="kw-chip" onClick={() => setKeyword(c)}>
                {c}
              </div>
            ))}
          </div>
          <button
            className="gen-btn"
            type="button"
            disabled={loading || remaining <= 0}
            onClick={generate}
          >
            生成今晚的故事脚本 ✨
          </button>
          <div className="usage-note">{remainingText}</div>
          {error && (
            <div className="error-state">
              <span className="error-icon">😿</span>
              <div className="error-msg">{error}</div>
              <button className="retry-btn" type="button" onClick={resetToInput}>
                重新试试
              </button>
            </div>
          )}
        </div>
      )}

      {view === 'loading' && (
        <div className="story-body">
          <div className="loading-state">
            <img className="loading-img" src={kekeAsset('hero/waiting.jpg')} alt="" />
            <div className="loading-text">
              今晚独属于你们的故事正在生成
              <span className="loading-dots" />
            </div>
            <div className="loading-sub">
              完整故事大概需要 30-60 秒
              <br />
              泡杯茶，马上就好 🌙
            </div>
          </div>
        </div>
      )}

      {view === 'story' && story && (
        <div className="story-body">
          <div className="story-scroll">
            <div className="story-cover">
              <div className="story-cover-label">睡前故事 · 波波动物城</div>
              <div className="story-cover-title">{story.title}</div>
              <div className="story-cover-kw">🌟 {story.keyword}</div>
            </div>
            <StoryBlocks blocks={story.blocks} />
          </div>
          <div className="story-actions show">
            <button className="action-btn action-again" type="button" onClick={resetToInput}>
              再讲一个
            </button>
            <button className="action-btn action-share" type="button" onClick={openShare}>
              保存 / 分享 📤
            </button>
          </div>
        </div>
      )}

      {shareOpen && story && (
        <ShareModal
          story={story}
          onClose={() => setShareOpen(false)}
          onLongImageReady={onLongImageReady}
        />
      )}
      {toast && <div className="keke-toast show">{toast}</div>}
    </div>
  )
}
