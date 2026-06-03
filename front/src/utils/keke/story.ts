import type { KekeStory, KekeStoryBlock } from '@/types'

/**
 * Parse the raw DeepSeek response into a renderable story.
 * Ported verbatim from H5 § parseStory.
 *
 *   [TITLE]雨天的客人[/TITLE]
 *   [STORY]
 *   哗啦啦下雨了……
 *   【问孩子】你下雨天会做什么？
 *   …
 *   [/STORY]
 *
 * Tags inside the body — 【问孩子】 / 【动作】 / 【预测】 — become
 * separate blocks so the page can style each interactively.
 */
export function parseStory(raw: string, keyword: string): KekeStory {
  const titleMatch = raw.match(/\[TITLE\]([\s\S]*?)\[\/TITLE\]/) ?? raw.match(/【标题】([^\n]+)/)
  const storyMatch =
    raw.match(/\[STORY\]([\s\S]*?)\[\/STORY\]/) ?? raw.match(/【故事】([\s\S]*?)【结束】/)

  const title = titleMatch ? titleMatch[1].trim() : `呼噜和可可的${keyword}故事`
  const storyRaw = storyMatch ? storyMatch[1].trim() : raw

  const blocks: KekeStoryBlock[] = []
  let paraBuffer: string[] = []
  const flushPara = () => {
    if (paraBuffer.length > 0) {
      blocks.push({ type: 'para', text: paraBuffer.join('') })
      paraBuffer = []
    }
  }

  for (const line of storyRaw.split('\n')) {
    const t = line.trim()
    if (!t) continue
    const q = t.match(/^【问孩子】(.+)/)
    const a = t.match(/^【动作】(.+)/)
    const p = t.match(/^【预测】(.+)/)
    if (q) {
      flushPara()
      blocks.push({ type: 'question', text: q[1] })
    } else if (a) {
      flushPara()
      blocks.push({ type: 'action', text: a[1] })
    } else if (p) {
      flushPara()
      blocks.push({ type: 'predict', text: p[1] })
    } else {
      paraBuffer.push(t)
    }
  }
  flushPara()

  return { title, blocks, keyword, time: Date.now() }
}
