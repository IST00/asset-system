import { Skeleton } from 'antd'
import { Box, Building2, CircleDollarSign, MessageSquareText, ShieldCheck } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import SectionPanel from '@/components/ui/SectionPanel'

const loadingSections: ReadonlyArray<{
  key: 'basic' | 'ownership' | 'purchase' | 'management' | 'remark'
  titleKey: string
  icon: LucideIcon
  fieldCount: number
}> = [
  { key: 'basic', titleKey: 'assets.form.sections.basic', icon: Box, fieldCount: 4 },
  {
    key: 'ownership',
    titleKey: 'assets.form.sections.ownership',
    icon: Building2,
    fieldCount: 4,
  },
  {
    key: 'purchase',
    titleKey: 'assets.form.sections.purchase',
    icon: CircleDollarSign,
    fieldCount: 4,
  },
  {
    key: 'management',
    titleKey: 'assets.form.sections.management',
    icon: ShieldCheck,
    fieldCount: 2,
  },
  {
    key: 'remark',
    titleKey: 'assets.form.sections.remark',
    icon: MessageSquareText,
    fieldCount: 1,
  },
]

export default function AssetFormLoading() {
  const { t } = useTranslation()
  return (
    <div className="asset-form__loading-sections">
      {loadingSections.map((section) => {
        const Icon = section.icon
        return (
          <SectionPanel
            key={section.key}
            title={t(section.titleKey)}
            icon={<Icon aria-hidden="true" size={18} />}
          >
            <div className="asset-form__loading-grid">
              {Array.from({ length: section.fieldCount }, (_, index) => {
                const wide = section.key === 'remark' || (section.key === 'basic' && index === 0)
                return (
                  <div
                    key={`${section.key}-${index}`}
                    className={`asset-form__loading-field${wide ? ' asset-form__loading-field--wide' : ''}`}
                  >
                    <Skeleton.Input className="asset-form__loading-label" active size="small" />
                    <Skeleton.Input className="asset-form__loading-control" active block />
                  </div>
                )
              })}
            </div>
          </SectionPanel>
        )
      })}
    </div>
  )
}
