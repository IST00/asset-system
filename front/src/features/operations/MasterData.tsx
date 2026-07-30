import { Button, Input, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Boxes, ChevronRight, Database, FolderTree, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  masterDataApi,
  type ReferenceItem,
  type SupplierItem,
  type TreeItem,
} from '@/api/administration'
import StatePanel from '@/components/ui/StatePanel'
import {
  GlassPanel,
  OperationsHero,
  OperationsMetrics,
  SectionHeading,
  StatusPill,
} from './OperationsUI'

interface MasterNode {
  code: string
  name: string
  detail: string
  status: string
  children: number
  depth: number
}

interface MasterGroup {
  key: string
  label: string
  description: string
  nodes: MasterNode[]
}

function flattenTree(items: TreeItem[], depth = 0): MasterNode[] {
  return items.flatMap((item) => [
    {
      code: item.code,
      name: item.name,
      detail: depth ? `第 ${depth + 1} 级节点` : '顶级节点',
      status: item.status,
      children: item.children?.length ?? 0,
      depth,
    },
    ...flattenTree(item.children ?? [], depth + 1),
  ])
}

function referenceNodes(items: ReferenceItem[], detail: string): MasterNode[] {
  return items.map((item) => ({
    code: item.code,
    name: item.name,
    detail,
    status: item.status,
    children: 0,
    depth: 0,
  }))
}

function supplierNodes(items: SupplierItem[]): MasterNode[] {
  return items.map((item) => ({
    code: item.code,
    name: item.name,
    detail: item.contact_name ? `联系人：${item.contact_name}` : '未设置联系人',
    status: item.status,
    children: 0,
    depth: 0,
  }))
}

function isEnabled(status: string): boolean {
  return ['ENABLED', 'ACTIVE'].includes(status.toUpperCase())
}

export default function MasterData() {
  const [activeKey, setActiveKey] = useState('organizations')
  const [keyword, setKeyword] = useState('')
  const query = useQuery({
    queryKey: ['master-data', 'overview'],
    queryFn: async () => {
      const [categories, units, sources, locations, suppliers, organizations] = await Promise.all([
        masterDataApi.categories(),
        masterDataApi.units(),
        masterDataApi.sources(),
        masterDataApi.locations(),
        masterDataApi.suppliers(),
        masterDataApi.organizations(),
      ])
      return { categories, units, sources, locations, suppliers, organizations }
    },
  })

  const groups = useMemo<MasterGroup[]>(() => {
    const data = query.data
    return [
      {
        key: 'organizations',
        label: '组织架构',
        description: '公司与部门的层级结构，数据来自组织树接口。',
        nodes: flattenTree(data?.organizations ?? []),
      },
      {
        key: 'categories',
        label: '资产分类',
        description: '资产分类及上下级关系，数据来自资产分类树接口。',
        nodes: flattenTree(data?.categories ?? []),
      },
      {
        key: 'locations',
        label: '存放地点',
        description: '城市、园区、楼层和区域的地点层级。',
        nodes: flattenTree(data?.locations ?? []),
      },
      {
        key: 'units',
        label: '计量单位',
        description: '资产登记与库存统计使用的计量单位。',
        nodes: referenceNodes(data?.units ?? [], '计量单位'),
      },
      {
        key: 'sources',
        label: '资产来源',
        description: '采购、调入等资产来源字典。',
        nodes: referenceNodes(data?.sources ?? [], '资产来源'),
      },
      {
        key: 'suppliers',
        label: '供应商',
        description: '采购入库可选择的供应商档案。',
        nodes: supplierNodes(data?.suppliers ?? []),
      },
    ]
  }, [query.data])
  const activeGroup = groups.find((group) => group.key === activeKey) ?? groups[0]
  const nodes = useMemo(() => {
    const normalized = keyword.trim().toLowerCase()
    if (!normalized) return activeGroup.nodes
    return activeGroup.nodes.filter((node) =>
      [node.code, node.name, node.detail].some((value) => value.toLowerCase().includes(normalized)),
    )
  }, [activeGroup, keyword])
  const activeCount = activeGroup.nodes.filter((node) => isEnabled(node.status)).length
  const organizationCount = groups.find((group) => group.key === 'organizations')?.nodes.length ?? 0
  const categoryCount = groups.find((group) => group.key === 'categories')?.nodes.length ?? 0
  const locationCount = groups.find((group) => group.key === 'locations')?.nodes.length ?? 0
  const supplierCount = groups.find((group) => group.key === 'suppliers')?.nodes.length ?? 0
  const totalNodes = groups.reduce((sum, group) => sum + group.nodes.length, 0)

  return (
    <div className="operations-page">
      <OperationsHero
        eyebrow="MASTER DATA"
        title="一套可信基础资料，支撑所有资产业务"
        description="组织、分类、地点、单位、来源和供应商均已连接后端，当前先提供真实数据查询。"
        icon={Database}
        tone="amber"
        actions={
          <>
            <Button type="primary" size="large" disabled>
              新增功能待接入
            </Button>
            <Button size="large" icon={<FolderTree size={17} />} disabled>
              层级校验待开放
            </Button>
          </>
        }
        aside={
          <div className="operations-hero__aside-card">
            <span>基础资料记录</span>
            <strong>{totalNodes}</strong>
            <small>当前六类后端基础数据</small>
          </div>
        }
      />

      <OperationsMetrics
        items={[
          { label: '公司与部门', value: organizationCount, hint: '后端组织树节点', tone: 'blue' },
          { label: '资产分类', value: categoryCount, hint: '含所有层级', tone: 'violet' },
          { label: '地点节点', value: locationCount, hint: '含所有层级', tone: 'cyan' },
          { label: '供应商档案', value: supplierCount, hint: '当前可查询记录', tone: 'amber' },
        ]}
      />

      <GlassPanel>
        {query.isLoading ? (
          <div className="operations-loading">
            <Spin />
          </div>
        ) : query.isError ? (
          <StatePanel
            mode="error"
            message="基础资料加载失败，请确认后端服务和当前账号权限"
            retryLabel="重新加载"
            onRetry={() => void query.refetch()}
          />
        ) : (
          <div className="operations-master-layout">
            <nav className="operations-master-menu" aria-label="基础资料类型">
              {groups.map((group) => (
                <button
                  key={group.key}
                  type="button"
                  className={group.key === activeGroup.key ? 'is-active' : ''}
                  onClick={() => {
                    setActiveKey(group.key)
                    setKeyword('')
                  }}
                >
                  <span>{group.label}</span>
                  <small>{group.nodes.length}</small>
                </button>
              ))}
            </nav>

            <div>
              <SectionHeading
                eyebrow="DICTIONARY"
                title={activeGroup.label}
                description={activeGroup.description}
                action={<StatusPill label="真实后端数据" tone="green" />}
              />
              <div className="operations-toolbar">
                <Input
                  value={keyword}
                  allowClear
                  prefix={<Search aria-hidden="true" size={15} />}
                  placeholder={`搜索${activeGroup.label}编码或名称`}
                  onChange={(event) => setKeyword(event.target.value)}
                />
                <div className="operations-toolbar__filters">
                  <StatusPill label={`${activeCount} 个在用`} tone="green" />
                  <StatusPill
                    label={`${activeGroup.nodes.length - activeCount} 个停用`}
                    tone="slate"
                  />
                </div>
              </div>
              {nodes.length ? (
                <div className="operations-task-list">
                  {nodes.map((node, index) => (
                    <div
                      key={`${node.code}-${index}`}
                      className={`operations-master-node operations-tone--${index % 2 ? 'cyan' : 'amber'}`}
                      style={{ marginLeft: Math.min(node.depth * 18, 54) }}
                    >
                      <span className="operations-master-node__icon">{node.code.slice(0, 4)}</span>
                      <div className="operations-master-node__content">
                        <strong>{node.name}</strong>
                        <span>
                          {node.code} · {node.detail}
                          {node.children ? ` · ${node.children} 个直接下级` : ''}
                        </span>
                      </div>
                      <div className="operations-master-node__actions">
                        <StatusPill
                          label={isEnabled(node.status) ? '在用' : '停用'}
                          tone={isEnabled(node.status) ? 'green' : 'slate'}
                        />
                        <ChevronRight aria-hidden="true" size={16} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="operations-empty-note">
                  <Boxes size={24} />
                  <br />
                  没有匹配的基础资料
                </div>
              )}
            </div>
          </div>
        )}
      </GlassPanel>
    </div>
  )
}
