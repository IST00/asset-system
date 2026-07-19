import { Button } from 'antd'
import { CircleAlert, Inbox } from 'lucide-react'
import './ui.css'

interface StatePanelProps {
  mode: 'empty' | 'error'
  message: string
  retryLabel?: string
  onRetry?: () => void
}

export default function StatePanel({ mode, message, retryLabel, onRetry }: StatePanelProps) {
  const Icon = mode === 'error' ? CircleAlert : Inbox

  return (
    <div
      className={`asset-state-panel asset-state-panel--${mode}`}
      role={mode === 'error' ? 'alert' : 'status'}
    >
      <Icon aria-hidden="true" size={30} strokeWidth={1.7} />
      <p>{message}</p>
      {onRetry && retryLabel ? (
        <Button onClick={onRetry} type="primary">
          {retryLabel}
        </Button>
      ) : null}
    </div>
  )
}
