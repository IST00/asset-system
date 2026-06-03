import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useKekeStore } from '@/store/keke'
import { HISTORY_MAX, loadHistory } from '@/utils/keke/history'

function formatTime(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function History() {
  const navigate = useNavigate()
  const setCurrentStory = useKekeStore((s) => s.setCurrentStory)
  // localStorage is sync — no need for state. Re-reads when this page mounts.
  const list = useMemo(() => loadHistory(), [])

  return (
    <div className="page-history">
      <div className="gallery-header">
        <button
          className="back-btn"
          type="button"
          onClick={() => navigate('/keke/home')}
        >
          ←
        </button>
        <div className="gallery-header-title">以前的故事</div>
      </div>
      <div className="history-list">
        {list.length === 0 ? (
          <div className="history-empty">
            还没有生成过故事哦 🌙
            <br />
            回去生成第一个吧～
          </div>
        ) : (
          <>
            <div className="history-note">
              📌 这里只保留最近 {HISTORY_MAX} 篇故事。
              <br />
              喜欢的故事记得用"保存/分享"导出长图存下来，不然会被新故事顶掉哦～
            </div>
            {list.map((item, i) => (
              <div
                key={`${item.time}-${i}`}
                className="history-item"
                onClick={() => {
                  setCurrentStory(item)
                  navigate('/keke/story')
                }}
              >
                <div className="history-item-title">{item.title}</div>
                <div className="history-item-meta">
                  🌟 {item.keyword} · {formatTime(item.time)}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
