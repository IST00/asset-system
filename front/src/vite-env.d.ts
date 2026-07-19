/// <reference types="vite/client" />

import type { SoybeanCommonMain } from '@soybean/types.main'
import type * as React from 'react'
import type * as ReactDOM from 'react-dom'

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

declare global {
  interface Window {
    React: typeof React
    ReactDOM: typeof ReactDOM
    SoybeanCommonMain: SoybeanCommonMain
    pagePath: string
    setupWKWebViewJavascriptBridge: unknown
    WKWebViewJavascriptBridge: unknown
    WKWVJBCallbacks: unknown
    webkit: unknown
    SoybeanCoreMain: unknown
    javaDataPath: string
    deeplinkPath: string
  }
}
