import type { ReactNode } from 'react'
import './ui.css'

interface SectionPanelProps {
  title: string
  icon?: ReactNode
  extra?: ReactNode
  className?: string
  children: ReactNode
}

export default function SectionPanel({
  title,
  icon,
  extra,
  className,
  children,
}: SectionPanelProps) {
  const classes = ['asset-section-panel', className].filter(Boolean).join(' ')

  return (
    <section className={classes}>
      <div className="asset-section-panel__header">
        <div className="asset-section-panel__title">
          {icon}
          <h2>{title}</h2>
        </div>
        {extra ? <div className="asset-section-panel__extra">{extra}</div> : null}
      </div>
      <div className="asset-section-panel__body">{children}</div>
    </section>
  )
}
