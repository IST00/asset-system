import { useNavigate } from 'react-router-dom'

const HIGHLIGHTS = [
  {
    id: 'b1',
    num: '1',
    emoji: '🎁',
    title: '千人千面',
    desc: '娃出"关键词"即可生成自己的专属故事',
  },
  {
    id: 'b2',
    num: '2',
    emoji: '🧠',
    title: '脑科学设计',
    desc: '用熟悉的心理图式给孩子最适度的认知增量',
  },
  {
    id: 'b3',
    num: '3',
    emoji: '👨‍👧',
    title: '联合注意',
    desc: '提示家长做引导互动，给孩子语言学习、情感共鸣与社交沟通打地基',
  },
  {
    id: 'b4',
    num: '4',
    emoji: '🌱',
    title: '长出好品格',
    desc: '在故事里融入了情绪安全、社交能力、想象力、抗挫力、边界意识、家庭平等、内在动力、尊重个体等教育理念',
  },
] as const

export default function Intro() {
  const navigate = useNavigate()
  const leave = () => navigate('/keke/home')

  return (
    <div className="page-intro">
      <button className="intro-skip" type="button" onClick={leave}>
        跳过 →
      </button>
      <div className="intro-wrap">
        <div className="intro-brand">
          爱孩子、懂孩子的<strong>波波龟工作室</strong>（樊登漫画团队）
          <br />
          为<strong>3-6岁</strong>小朋友推出
        </div>
        <div className="intro-title">
          呼噜与可可的
          <br />
          欢乐时光
        </div>
        <div className="intro-subtitle">睡前故事生成器</div>

        <div className="intro-highlights-title">四大亮点</div>

        <div className="intro-balls">
          {HIGHLIGHTS.map((h) => (
            <div key={h.id} className={`intro-ball ${h.id}`}>
              <div className="intro-ball-num">{h.num}</div>
              <div className="intro-ball-emoji">{h.emoji}</div>
              <div className="intro-ball-title">{h.title}</div>
              <div className="intro-ball-desc">{h.desc}</div>
            </div>
          ))}
        </div>

        <div className="intro-tagline">
          故事<strong>有料不瞎编</strong>，
          <br />
          今晚就解放家长的嗓子吧！
        </div>

        <button className="intro-cta" type="button" onClick={leave}>
          开始今晚的故事 ✨
        </button>
        <div className="intro-footnote">不用注册、不用下载，打开就讲</div>
      </div>
    </div>
  )
}
