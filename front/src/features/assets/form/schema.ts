import { z } from 'zod'

const requiredString = (message: string) =>
  z.string({ required_error: message, invalid_type_error: message }).trim().min(1, message)
const optionalString = z.string().optional()

export const assetFormSchema = z
  .object({
    asset_name: requiredString('assets.form.errors.assetNameRequired'),
    company_name: requiredString('assets.form.errors.companyRequired'),
    category_name: requiredString('assets.form.errors.categoryRequired'),
    source_name: requiredString('assets.form.errors.sourceRequired'),
    unit_name: requiredString('assets.form.errors.unitRequired'),
    supplier_name: optionalString,
    purchase_date: requiredString('assets.form.errors.purchaseDateRequired'),
    location_name: requiredString('assets.form.errors.locationRequired'),
    purchase_amount: z
      .number({
        required_error: 'assets.form.errors.required',
        invalid_type_error: 'assets.form.errors.required',
      })
      .min(0, 'assets.form.errors.amountNonNegative'),
    zero_amount_reason: optionalString,
    model: optionalString,
    serial_number: optionalString,
    manager_name: requiredString('assets.form.errors.managerRequired'),
    rfid_tag: optionalString,
    change_reason: optionalString,
    remark: optionalString,
  })
  .superRefine((values, context) => {
    if (values.purchase_amount === 0 && !values.zero_amount_reason?.trim()) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'assets.form.errors.zeroAmountReason',
        path: ['zero_amount_reason'],
      })
    }
  })

export type AssetFormInput = z.infer<typeof assetFormSchema>

export type AssetFormMode = { mode: 'create' } | { mode: 'edit'; assetId: number }

export function getAssetFormMode(assetId: string | undefined): AssetFormMode | null {
  if (assetId === undefined) return { mode: 'create' }
  if (!/^\d+$/.test(assetId)) return null

  const parsedAssetId = Number(assetId)
  return Number.isSafeInteger(parsedAssetId) && parsedAssetId > 0
    ? { mode: 'edit', assetId: parsedAssetId }
    : null
}
