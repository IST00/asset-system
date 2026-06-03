import { Navigate, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Spin } from 'antd'
import ProtectedRoute from './ProtectedRoute'
import Layout from '@/components/Layout'

const Login = lazy(() => import('@/pages/Login'))
const Home = lazy(() => import('@/pages/Home'))
const NotFound = lazy(() => import('@/pages/NotFound'))

// Keke (呼噜与可可) H5 — public, no auth required.
const KekeLayout = lazy(() => import('@/pages/keke/Layout'))
const KekeIntro = lazy(() => import('@/pages/keke/Intro'))
const KekeHome = lazy(() => import('@/pages/keke/Home'))
const KekeGallery = lazy(() => import('@/pages/keke/Gallery'))
const KekeStory = lazy(() => import('@/pages/keke/Story'))
const KekeHistory = lazy(() => import('@/pages/keke/History'))

const loading = (
  <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
    <Spin />
  </div>
)

export default function AppRouter() {
  return (
    <Suspense fallback={loading}>
      <Routes>
        <Route path="/login" element={<Login />} />

        {/* Keke H5: public, mounted outside ProtectedRoute */}
        <Route path="/keke" element={<KekeLayout />}>
          <Route index element={<KekeIntro />} />
          <Route path="home" element={<KekeHome />} />
          <Route path="gallery" element={<KekeGallery />} />
          <Route path="story" element={<KekeStory />} />
          <Route path="history" element={<KekeHistory />} />
        </Route>

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/home" replace />} />
          <Route path="home" element={<Home />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
