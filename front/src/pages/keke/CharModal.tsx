import type { KekeCharacter } from '@/types'
import { kekeAvatarUrl } from '@/utils/keke/asset'

interface Props {
  character: KekeCharacter | null
  onClose: () => void
}

/**
 * Bottom-sheet modal showing one character's portrait + tagline.
 * Shared between Home (marquee tap) and Gallery (card tap).
 */
export default function CharModal({ character, onClose }: Props) {
  if (!character) return null
  return (
    <div className="char-modal" onClick={onClose}>
      <div className="char-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="char-sheet-handle" />
        <img
          className="char-sheet-img"
          src={kekeAvatarUrl(character.file)}
          alt={character.name}
        />
        <div className="char-sheet-name">{character.name}</div>
        <div className="char-sheet-role">{character.role}</div>
        <div className="char-sheet-desc">{character.desc}</div>
      </div>
    </div>
  )
}
