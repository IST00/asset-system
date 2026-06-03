import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { KekeStory } from '@/types'

/**
 * Currently-displayed story shared between Story and History pages.
 * Persisted to localStorage so a refresh on the Story page keeps the
 * generated content visible.
 */
interface KekeState {
  currentStory: KekeStory | null
  setCurrentStory: (s: KekeStory | null) => void
}

export const useKekeStore = create<KekeState>()(
  persist(
    (set) => ({
      currentStory: null,
      setCurrentStory: (currentStory) => set({ currentStory }),
    }),
    { name: 'keke' },
  ),
)
