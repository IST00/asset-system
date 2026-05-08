/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_API_TARGET: string
  readonly VITE_API_PREFIX: string
  readonly VITE_APP_BASE: string
  readonly VITE_APP_TITLE: string
  readonly VITE_APP_DESCRIPTION: string
  readonly VITE_DISABLE_SENSORS: string
  readonly VITE_IS_IPAD: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
