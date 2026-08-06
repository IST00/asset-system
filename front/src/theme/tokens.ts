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
  glass: {
    surface: 'rgba(255, 255, 255, 0.68)',
    surfaceStrong: 'rgba(255, 255, 255, 0.84)',
    border: 'rgba(255, 255, 255, 0.78)',
    highlight: 'rgba(255, 255, 255, 0.92)',
    blur: 24,
  },
  shadow: {
    floating: '0 18px 48px rgba(31, 62, 112, 0.14)',
    glass: '0 18px 44px rgba(31, 62, 112, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.82)',
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
      "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif",
  },
  components: {
    Button: {
      controlHeight: 42,
      controlHeightLG: 46,
      controlHeightSM: 34,
      borderRadius: 11,
      borderRadiusLG: 12,
      borderRadiusSM: 9,
      fontWeight: 600,
      paddingInline: 16,
      paddingInlineLG: 18,
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
