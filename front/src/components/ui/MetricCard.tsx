import type { LucideIcon } from 'lucide-react'
import './ui.css'

export type MetricTone = 'brand' | 'success' | 'warning' | 'danger'

interface MetricCardProps {
  icon: LucideIcon
  label: string
  value: number | string
  unit?: string
  tone?: MetricTone
  change?: string
}

export default function MetricCard({
  icon: Icon,
  label,
  value,
  unit,
  tone = 'brand',
  change,
}: MetricCardProps) {
  return (
    <article className={`asset-metric-card asset-metric-card--${tone}`}>
      <div className="asset-metric-card__topline">
        <span className="asset-metric-card__icon">
          <Icon aria-hidden="true" size={20} strokeWidth={1.9} />
        </span>
        {change ? <span className="asset-metric-card__change">{change}</span> : null}
      </div>
      <div className="asset-metric-card__value">
        <strong>{value}</strong>
        {unit ? <span>{unit}</span> : null}
      </div>
      <p>{label}</p>
    </article>
  )
}
