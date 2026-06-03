import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { KekeCharacter, KekeCharacterGroup } from '@/types'
import { CHARACTERS } from '@/utils/keke/characters'
import { kekeAvatarUrl } from '@/utils/keke/asset'
import CharModal from './CharModal'

const GROUPS: KekeCharacterGroup[] = ['核心家庭', '玩伴', '城市大人']

export default function Gallery() {
  const navigate = useNavigate()
  const [active, setActive] = useState<KekeCharacter | null>(null)

  return (
    <div className="page-gallery">
      <div className="gallery-header">
        <button
          className="back-btn"
          type="button"
          onClick={() => navigate('/keke/home')}
        >
          ←
        </button>
        <div className="gallery-header-title">波波动物城的朋友们</div>
      </div>

      {GROUPS.map((group) => (
        <div key={group}>
          <div className="gallery-group-label">{group}</div>
          <div className="gallery-grid">
            {CHARACTERS.filter((c) => c.group === group).map((c) => (
              <div
                key={c.name}
                className="gallery-card"
                onClick={() => setActive(c)}
              >
                <img
                  className="gallery-card-img"
                  src={kekeAvatarUrl(c.file)}
                  alt={c.name}
                  loading="lazy"
                />
                <div className="gallery-card-name">{c.name}</div>
                <div className="gallery-card-role">{c.role}</div>
                <div className="gallery-card-desc">{c.desc}</div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="gallery-bottom" />
      <CharModal character={active} onClose={() => setActive(null)} />
    </div>
  )
}
