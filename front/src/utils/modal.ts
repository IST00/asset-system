import { Modal } from 'antd'

export const confirm = (content: string, onOk: () => void) =>
  Modal.confirm({ title: '确认', content, onOk })
