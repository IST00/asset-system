import type { CsvAssetImportRow } from '@/api/assets'

export const csvHeaders = [
  '所属公司',
  '资产名称',
  '资产分类',
  '计量单位',
  '原值',
  '零金额原因',
  '采购日期',
  '供应商',
  '责任管理员',
  '资产来源',
  '存放地点',
  '规格型号',
  '序列号',
  'RFID',
  '备注',
] as const

export interface ParsedImportRow {
  line: number
  values: Record<string, string>
  data?: CsvAssetImportRow
  errors: string[]
}

export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        cell += '"'
        index += 1
      } else {
        quoted = !quoted
      }
    } else if (char === ',' && !quoted) {
      row.push(cell.trim())
      cell = ''
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[index + 1] === '\n') index += 1
      row.push(cell.trim())
      if (row.some((value) => value)) rows.push(row)
      row = []
      cell = ''
    } else {
      cell += char
    }
  }
  row.push(cell.trim())
  if (row.some((value) => value)) rows.push(row)
  return rows
}

const requiredHeaders = [
  '所属公司',
  '资产名称',
  '资产分类',
  '计量单位',
  '原值',
  '采购日期',
  '责任管理员',
  '资产来源',
  '存放地点',
]

export function validateImportCsv(text: string): ParsedImportRow[] {
  const rows = parseCsv(text.replace(/^\uFEFF/, ''))
  if (!rows.length) throw new Error('CSV 文件为空')
  const headers = rows[0].map((item) => item.trim())
  const missing = requiredHeaders.filter((header) => !headers.includes(header))
  if (missing.length) throw new Error(`模板缺少列：${missing.join('、')}`)
  if (rows.length === 1) throw new Error('CSV 文件只有表头，没有资产数据')
  if (rows.length - 1 > 100) throw new Error('单次导入最多 100 条资产')

  const serials = new Set<string>()
  const rfids = new Set<string>()
  const organizations = new Set<string>()
  const parsed = rows.slice(1).map<ParsedImportRow>((cells, rowIndex) => {
    const values = Object.fromEntries(
      headers.map((header, index) => [header, cells[index]?.trim() ?? '']),
    )
    const errors: string[] = []
    requiredHeaders.forEach((header) => {
      if (!values[header]) errors.push(`${header}不能为空`)
    })
    const amount = Number(values['原值'])
    if (!Number.isFinite(amount) || amount < 0) errors.push('原值必须是大于或等于 0 的数字')
    if (amount === 0 && !values['零金额原因']) errors.push('零金额资产必须填写原因')
    if (values['采购日期'] && !/^\d{4}-\d{2}-\d{2}$/.test(values['采购日期'])) {
      errors.push('采购日期必须使用 YYYY-MM-DD 格式')
    }
    const serial = values['序列号']?.toLowerCase()
    if (serial) {
      if (serials.has(serial)) errors.push('序列号在文件内重复')
      serials.add(serial)
    }
    const rfid = values.RFID?.toLowerCase()
    if (rfid) {
      if (rfids.has(rfid)) errors.push('RFID 在文件内重复')
      rfids.add(rfid)
    }
    if (values['所属公司']) organizations.add(values['所属公司'])
    return {
      line: rowIndex + 2,
      values,
      errors,
      data: errors.length
        ? undefined
        : {
            organization_name: values['所属公司'],
            asset_name: values['资产名称'],
            category_name: values['资产分类'],
            unit_name: values['计量单位'],
            original_amount: amount,
            zero_amount_reason: values['零金额原因'] || undefined,
            purchase_date: values['采购日期'],
            supplier_name: values['供应商'] || undefined,
            manager_name: values['责任管理员'],
            source_name: values['资产来源'],
            location_name: values['存放地点'],
            specification_model: values['规格型号'] || undefined,
            serial_number: values['序列号'] || undefined,
            rfid_tag: values.RFID || undefined,
            remark: values['备注'] || undefined,
          },
    }
  })
  if (organizations.size > 1) {
    parsed.forEach((row) => row.errors.push('同一个文件只能包含一个所属公司'))
  }
  return parsed
}

export function toCsvCell(value: unknown): string {
  const text = String(value ?? '')
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}
