import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Space, Upload, message } from 'antd'
import { Camera } from 'lucide-react'
import {
  attachmentApi,
  type AssetAttachmentType,
  type AssetAttachmentDocumentType,
} from '@/api/attachments'

interface EvidenceAsset {
  asset_id: number
  asset_code: string | null
  asset_name: string
}

interface WorkflowEvidenceUploadProps {
  businessId: number
  businessType: Extract<
    AssetAttachmentType,
    'USAGE_SIGN' | 'RETURN_HANDOVER' | 'RETURN_INSPECTION' | 'TRANSFER_RECEIPT'
  >
  documentType: Extract<
    AssetAttachmentDocumentType,
    | 'SIGN_PHOTO'
    | 'RETURN_PHOTO'
    | 'INSPECTION_PHOTO'
    | 'TRANSFER_RECEIPT_PHOTO'
    | 'ELECTRONIC_SIGNATURE'
  >
  assets: EvidenceAsset[]
  label: string
}

export default function WorkflowEvidenceUpload({
  businessId,
  businessType,
  documentType,
  assets,
  label,
}: WorkflowEvidenceUploadProps) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: ({ assetId, file }: { assetId: number; file: File }) =>
      attachmentApi.upload(assetId, {
        businessType,
        businessId,
        documentType,
        file,
      }),
    onSuccess: async () => {
      await message.success('证据附件已上传')
      await queryClient.invalidateQueries({ queryKey: ['asset-attachments'] })
      await queryClient.invalidateQueries({ queryKey: ['workbench'] })
    },
    onError: (error: Error) => void message.error(error.message),
  })

  return (
    <Space wrap size={[8, 8]}>
      <span style={{ color: '#64748b', fontSize: 12 }}>{label}</span>
      {assets.map((asset) => (
        <Upload
          key={asset.asset_id}
          accept="image/*,.pdf"
          maxCount={1}
          showUploadList={false}
          beforeUpload={(file) => {
            mutation.mutate({ assetId: asset.asset_id, file })
            return Upload.LIST_IGNORE
          }}
          disabled={mutation.isPending}
        >
          <Button size="small" icon={<Camera size={13} />} loading={mutation.isPending}>
            {asset.asset_code ?? asset.asset_name}
          </Button>
        </Upload>
      ))}
    </Space>
  )
}
