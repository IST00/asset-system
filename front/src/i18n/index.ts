import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { zhCNResources } from './zhCN'

void i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': {
      translation: zhCNResources,
    },
  },
  lng: 'zh-CN',
  fallbackLng: 'zh-CN',
  interpolation: {
    escapeValue: false,
  },
})

export default i18n
