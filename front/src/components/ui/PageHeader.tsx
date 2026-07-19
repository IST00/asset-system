import type { ReactNode } from 'react'
import './ui.css'

interface PageHeaderProps {
  title: string
  description?: string
  meta?: ReactNode
  actions?: ReactNode
}

export default function PageHeader({ title, description, meta, actions }: PageHeaderProps) {
  return (
    <header className="asset-page-header">
      <div className="asset-page-header__copy">
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {meta || actions ? (
        <div className="asset-page-header__aside">
          {meta ? <div className="asset-page-header__meta">{meta}</div> : null}
          {actions ? <div className="asset-page-header__actions">{actions}</div> : null}
        </div>
      ) : null}
    </header>
  )
}
