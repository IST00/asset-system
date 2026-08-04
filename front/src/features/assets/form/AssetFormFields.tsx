import type { ReactNode } from 'react'
import { Controller } from 'react-hook-form'
import type { Control, FieldError, FieldErrors } from 'react-hook-form'
import { DatePicker, Form, Input, InputNumber, Select } from 'antd'
import dayjs from 'dayjs'
import { useTranslation } from 'react-i18next'
import type { AssetFormInput } from './schema'

const selectPopupClassNames = { popup: { root: 'asset-form-select-popup' } }
const datePopupClassNames = { popup: { root: 'asset-form-date-popup' } }

type TextFieldName = 'asset_name' | 'model' | 'serial_number' | 'rfid_tag' | 'zero_amount_reason'
type SelectFieldName =
  | 'company_name'
  | 'category_name'
  | 'source_name'
  | 'unit_name'
  | 'supplier_name'
  | 'location_name'
  | 'manager_name'

export interface AssetFormFieldsContext {
  control: Control<AssetFormInput>
  errors: FieldErrors<AssetFormInput>
}

interface FormFieldFrameProps {
  children: ReactNode
  error?: FieldError
  id: string
  label: string
  required?: boolean
  wide?: boolean
}

function FormFieldFrame({
  children,
  error,
  id,
  label,
  required = false,
  wide = false,
}: FormFieldFrameProps) {
  const { t } = useTranslation()
  const errorId = `${id}-error`
  return (
    <Form.Item
      className={`asset-form__field${wide ? ' asset-form__field--wide' : ''}`}
      label={label}
      required={required}
      htmlFor={id}
      validateStatus={error ? 'error' : undefined}
      help={error?.message ? <span id={errorId}>{t(error.message)}</span> : undefined}
    >
      {children}
    </Form.Item>
  )
}

const getFieldId = (name: string) => `asset-form-${name.replace(/_/g, '-')}`

export interface TextFormFieldProps extends AssetFormFieldsContext {
  name: TextFieldName
  label: string
  placeholder: string
  required?: boolean
  wide?: boolean
}

export function TextFormField({
  control,
  errors,
  name,
  label,
  placeholder,
  required,
  wide,
}: TextFormFieldProps) {
  const id = getFieldId(name)
  const error = errors[name]
  return (
    <FormFieldFrame id={id} label={label} required={required} wide={wide} error={error}>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <Input
            name={field.name}
            ref={field.ref}
            value={field.value ?? ''}
            onBlur={field.onBlur}
            onChange={field.onChange}
            id={id}
            placeholder={placeholder}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? `${id}-error` : undefined}
          />
        )}
      />
    </FormFieldFrame>
  )
}

export interface SelectFormFieldProps extends AssetFormFieldsContext {
  name: SelectFieldName
  label: string
  placeholder: string
  options: Array<{ label: string; value: string }>
  allowClear?: boolean
  disabled?: boolean
  required?: boolean
}

export function SelectFormField({
  control,
  errors,
  name,
  label,
  placeholder,
  options,
  allowClear,
  disabled,
  required,
}: SelectFormFieldProps) {
  const id = getFieldId(name)
  const error = errors[name]
  return (
    <FormFieldFrame id={id} label={label} required={required} error={error}>
      <Controller
        control={control}
        name={name}
        render={({ field }) =>
          disabled ? (
            <Input
              name={field.name}
              ref={field.ref}
              value={field.value ?? ''}
              onBlur={field.onBlur}
              onChange={field.onChange}
              id={id}
              disabled
            />
          ) : (
            <Select<string>
              {...field}
              id={id}
              allowClear={allowClear}
              showSearch
              options={options}
              classNames={selectPopupClassNames}
              placeholder={placeholder}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? `${id}-error` : undefined}
            />
          )
        }
      />
    </FormFieldFrame>
  )
}

export interface DateFormFieldProps extends AssetFormFieldsContext {
  label: string
  placeholder: string
}

export function DateFormField({ control, errors, label, placeholder }: DateFormFieldProps) {
  const name = 'purchase_date' as const
  const id = getFieldId(name)
  const error = errors[name]
  return (
    <FormFieldFrame id={id} label={label} required error={error}>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <DatePicker
            name={field.name}
            ref={field.ref}
            value={field.value ? dayjs(field.value) : null}
            onBlur={field.onBlur}
            onChange={(value) => field.onChange(value?.format('YYYY-MM-DD') ?? '')}
            id={id}
            classNames={datePopupClassNames}
            placeholder={placeholder}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? `${id}-error` : undefined}
          />
        )}
      />
    </FormFieldFrame>
  )
}

export interface AmountFormFieldProps extends AssetFormFieldsContext {
  label: string
  placeholder: string
}

export function AmountFormField({ control, errors, label, placeholder }: AmountFormFieldProps) {
  const name = 'purchase_amount' as const
  const id = getFieldId(name)
  const error = errors[name]
  return (
    <FormFieldFrame id={id} label={label} required error={error}>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <InputNumber<number>
            name={field.name}
            ref={field.ref}
            value={field.value}
            onBlur={field.onBlur}
            onChange={(value) => field.onChange(value ?? undefined)}
            id={id}
            min={0}
            precision={2}
            prefix="¥"
            placeholder={placeholder}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? `${id}-error` : undefined}
          />
        )}
      />
    </FormFieldFrame>
  )
}

export interface TextAreaFormFieldProps extends AssetFormFieldsContext {
  name?: 'remark' | 'change_reason'
  label: string
  placeholder: string
  required?: boolean
}

export function TextAreaFormField({
  control,
  errors,
  name = 'remark',
  label,
  placeholder,
  required,
}: TextAreaFormFieldProps) {
  const id = getFieldId(name)
  return (
    <FormFieldFrame id={id} label={label} wide error={errors[name]} required={required}>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <Input.TextArea
            name={field.name}
            ref={field.ref}
            value={field.value ?? ''}
            onBlur={field.onBlur}
            onChange={field.onChange}
            id={id}
            rows={4}
            maxLength={500}
            showCount
            placeholder={placeholder}
          />
        )}
      />
    </FormFieldFrame>
  )
}

export interface ReadOnlyFieldProps {
  label: string
  value: string
}

export function ReadOnlyField({ label, value }: ReadOnlyFieldProps) {
  return (
    <div className="asset-form__readonly-field">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
