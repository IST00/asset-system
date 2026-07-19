import type { ThemeConfig } from 'antd'

export const designTokens = {
  color: {
    brand: '#2563eb',
    brandHover: '#1d4ed8',
    brandSoft: '#eaf1ff',
    canvas: '#f5f7fb',
    surface: '#ffffff',
    surfaceMuted: '#f8fafc',
    border: '#e6eaf0',
    borderStrong: '#d7dde7',
    text: '#172033',
    textMuted: '#667085',
    textSubtle: '#98a2b3',
    success: '#169c68',
    successSoft: '#e8f7f1',
    warning: '#d97706',
    warningSoft: '#fff5df',
    danger: '#dc3545',
    dangerSoft: '#fff0f1',
    info: '#2f80ed',
    rail: '#172033',
  },
  radius: {
    small: 8,
    medium: 12,
    large: 16,
  },
  shadow: {
    floating: '0 14px 36px rgba(23, 32, 51, 0.12)',
  },
  layout: {
    railWidth: 72,
    maxContentWidth: 1440,
    mobileBreakpoint: 768,
  },
} as const

export const appTheme: ThemeConfig = {
  token: {
    colorPrimary: designTokens.color.brand,
    colorSuccess: designTokens.color.success,
    colorWarning: designTokens.color.warning,
    colorError: designTokens.color.danger,
    colorText: designTokens.color.text,
    colorTextSecondary: designTokens.color.textMuted,
    colorBorder: designTokens.color.border,
    colorBgLayout: designTokens.color.canvas,
    colorBgContainer: designTokens.color.surface,
    borderRadius: designTokens.radius.medium,
    fontFamily:
      "Inter, 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  components: {
    Button: {
      controlHeight: 40,
      borderRadius: designTokens.radius.small,
    },
    Drawer: {
      paddingLG: 20,
    },
    Menu: {
      itemBorderRadius: designTokens.radius.medium,
      itemHeight: 44,
    },
    Progress: {
      defaultColor: designTokens.color.brand,
      remainingColor: designTokens.color.brandSoft,
    },
  },
}
