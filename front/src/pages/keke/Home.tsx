import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { KekeCharacter } from '@/types'
import { CHARACTERS } from '@/utils/keke/characters'
import { kekeAsset, kekeAvatarUrl } from '@/utils/keke/asset'
import CharModal from './CharModal'

const HERO_IMAGES = ['hero/hero-1.jpg', 'hero/hero-2.jpg', 'hero/hero-3.jpg']
const HERO_INTERVAL_MS = 1300
const CITY_IMAGE = 'poster.png'

function MarqueeRow({
  list,
  row,
  onTap,
}: {
  list: KekeCharacter[]
  row: 'row1' | 'row2'
  onTap: (c: KekeCharacter) => void
}) {
  // duplicate for seamless scroll loop
  const items = useMemo(() => [...list, ...list], [list])
  return (
    <div className={`marquee ${row}`}>
      <div className="marquee-track">
        {items.map((c, idx) => (
          <div
            key={`${c.name}-${idx}`}
            className="char-avatar"
            onClick={() => onTap(c)}
          >
            <img
              className="char-avatar-img"
              src={kekeAvatarUrl(c.file)}
              alt={c.name}
              loading="lazy"
            />
            <div className="char-avatar-name">{c.name}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Home() {
  const navigate = useNavigate()
  const [heroIdx, setHeroIdx] = useState(0)
  const [activeChar, setActiveChar] = useState<KekeCharacter | null>(null)

  useEffect(() => {
    const id = window.setInterval(() => {
      setHeroIdx((i) => (i + 1) % HERO_IMAGES.length)
    }, HERO_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [])

  const half = Math.ceil(CHARACTERS.length / 2)
  const row1 = CHARACTERS.slice(0, half)
  const row2 = CHARACTERS.slice(half)

  return (
    <div className="page-home">
      <div className="home-hero">
        {HERO_IMAGES.map((src, i) => (
          <img
            key={src}
            className={`hero-img ${i === heroIdx ? 'active' : ''}`}
            src={kekeAsset(src)}
            alt="呼噜与可可"
          />
        ))}
        <div className="hero-overlay" />
        <div className="hero-text">
          <div className="hero-brand">帆书APP · 波波龟工作室出品</div>
          <div className="hero-title">
            呼噜与可可的
            <br />
            欢乐时光
          </div>
          <div className="hero-subtitle">家长陪读故事脚本生成器</div>
          <div className="scroll-hint">
            <span>了解这个故事世界</span>
            <span>↓</span>
          </div>
        </div>
      </div>

      <div className="home-city">
        <div className="city-card">
          <img className="city-img" src={kekeAsset(CITY_IMAGE)} alt="波波动物城的夜晚" />
          <div className="city-tag">✦ 波波动物城</div>
          <div className="city-title">一座充满故事的动物城市</div>
          <div className="city-desc">
            在波波动物城里，动物们和我们一样生活——有学校、书店、医院，还有温暖的家。
            <br />
            <br />
            <strong>呼噜和可可</strong>
            就住在这里。哥哥呼噜六岁，鲁莽又护妹妹；妹妹可可四岁，甜酷有主意。他们每天都在这座城市里，发生着许许多多
            <strong>有趣又奇妙的故事</strong>。
          </div>
        </div>
      </div>

      <div className="char-showcase">
        <div className="showcase-head">
          <div className="showcase-tag">✦ 故事里的朋友们</div>
          <div className="showcase-title">认识波波动物城的伙伴</div>
          <div className="showcase-sub">点一点头像，看看他们是谁</div>
        </div>
        <MarqueeRow list={row1} row="row1" onTap={setActiveChar} />
        <div style={{ height: 18 }} />
        <MarqueeRow list={row2} row="row2" onTap={setActiveChar} />
        <button
          className="showcase-allbtn"
          type="button"
          onClick={() => navigate('/keke/gallery')}
        >
          看看全部朋友 →
        </button>
      </div>

      <div className="home-start">
        <div className="divider" />
        <div className="start-section">
          <div className="start-title">今晚，你想听什么故事？</div>
          <div className="start-sub">
            让孩子说说今晚想听什么
            <br />
            AI马上为你们生成专属故事脚本
          </div>
          <button
            className="start-btn"
            type="button"
            onClick={() => navigate('/keke/story')}
          >
            开始今晚的故事 ✨
          </button>
          <div className="home-history-entry" onClick={() => navigate('/keke/history')}>
            📖 看看以前生成的故事
          </div>
        </div>
      </div>

      <CharModal character={activeChar} onClose={() => setActiveChar(null)} />
    </div>
  )
}
