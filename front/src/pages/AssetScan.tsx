import { useMutation } from '@tanstack/react-query'
import { Button, Card, Input, Segmented, Tag, message } from 'antd'
import { ArrowRight, ScanLine } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { scanLookup } from '@/api/assets'
import type { AssetSummary } from '@/features/assets/types'
import { GlassPanel, OperationsHero, SectionHeading } from '@/features/operations/OperationsUI'
import { assetStatusLabel } from '@/utils/displayLabels'

export default function AssetScan() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'asset_code' | 'rfid_tag'>('asset_code')
  const [value, setValue] = useState('')
  const [asset, setAsset] = useState<AssetSummary | null>(null)
  const lookup = useMutation({
    mutationFn: () => {
      const normalized = value.trim()
      if (!normalized)
        throw new Error(mode === 'asset_code' ? '请输入资产编码' : '请输入 RFID 标签')
      return scanLookup(
        mode === 'asset_code' ? { asset_code: normalized } : { rfid_tag: normalized },
      )
    },
    onSuccess: setAsset,
    onError: (error: Error) => {
      setAsset(null)
      void message.error(error.message)
    },
  })

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="SCAN ASSET"
        title="扫码 / RFID 查询资产"
        description="输入扫码设备识别出的资产编码或 RFID 标签，查询结果会遵守当前账号的数据权限。"
        icon={ScanLine}
        tone="cyan"
      />
      <GlassPanel>
        <SectionHeading
          eyebrow="LOOKUP"
          title="资产识别入口"
          description="暂不依赖飞书 SDK，手机浏览器、扫码枪和 RFID 读写器均可使用。"
        />
        <div className="operations-toolbar">
          <Segmented
            value={mode}
            onChange={(next) => setMode(next as typeof mode)}
            options={[
              { label: '资产编码', value: 'asset_code' },
              { label: 'RFID 标签', value: 'rfid_tag' },
            ]}
          />
          <Input.Search
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onSearch={() => lookup.mutate()}
            loading={lookup.isPending}
            enterButton="查询"
            placeholder={mode === 'asset_code' ? '例如 ZC-000123' : '例如 RFID-001'}
            allowClear
          />
        </div>
        {asset ? (
          <Card style={{ marginTop: 24 }}>
            <div className="operations-table__primary">
              <strong>{asset.asset_name}</strong>
              <span>{asset.asset_code}</span>
            </div>
            <div className="operations-grid operations-grid--three" style={{ marginTop: 16 }}>
              <span>分类：{asset.category_name}</span>
              <span>
                状态：<Tag>{assetStatusLabel(asset.status)}</Tag>
              </span>
              <span>使用人：{asset.user_name ?? '未分配'}</span>
              <span>组织：{asset.company_name}</span>
              <span>地点：{asset.location_name}</span>
              <span>管理员：{asset.manager_name ?? '未设置'}</span>
            </div>
            <Button
              type="primary"
              icon={<ArrowRight size={15} />}
              style={{ marginTop: 20 }}
              onClick={() => navigate(`/assets/${asset.id}`)}
            >
              查看资产详情
            </Button>
          </Card>
        ) : null}
      </GlassPanel>
    </div>
  )
}
