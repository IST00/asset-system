import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Tone } from './data'
import './Operations.css'

interface HeroProps {
  eyebrow: string
  title: string
  description: string
  icon: LucideIcon
  tone?: Tone
  actions?: ReactNode
  aside?: ReactNode
}

export function OperationsHero({
  eyebrow,
  title,
  description,
  icon: Icon,
  tone = 'blue',
  actions,
  aside,
}: HeroProps) {
  return (
    <section className={`operations-hero operations-tone--${tone}`}>
      <div className="operations-hero__orb" aria-hidden="true" />
      <div className="operations-hero__content">
        <span className="operations-hero__eyebrow">
          <Icon aria-hidden="true" size={16} strokeWidth={1.9} />
          {eyebrow}
        </span>
        <h1>{title}</h1>
        <p>{description}</p>
        {actions ? <div className="operations-hero__actions">{actions}</div> : null}
      </div>
      {aside ? <div className="operations-hero__aside">{aside}</div> : null}
    </section>
  )
}

interface MetricItem {
  label: string
  value: string | number
  hint?: string
  tone?: Tone
}

export function OperationsMetrics({ items }: { items: MetricItem[] }) {
  return (
    <section className="operations-metrics" aria-label="关键指标">
      {items.map((item) => (
        <article
          key={item.label}
          className={`operations-metric operations-tone--${item.tone ?? 'blue'}`}
        >
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          {item.hint ? <small>{item.hint}</small> : null}
        </article>
      ))}
    </section>
  )
}

export function StatusPill({ label, tone = 'slate' }: { label: string; tone?: Tone }) {
  return <span className={`operations-status operations-tone--${tone}`}>{label}</span>
}

interface SectionHeadingProps {
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
}

export function SectionHeading({ eyebrow, title, description, action }: SectionHeadingProps) {
  return (
    <header className="operations-section-heading">
      <div>
        {eyebrow ? <span>{eyebrow}</span> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div className="operations-section-heading__action">{action}</div> : null}
    </header>
  )
}

export function GlassPanel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={['operations-panel', className].filter(Boolean).join(' ')}>
      {children}
    </section>
  )
}
