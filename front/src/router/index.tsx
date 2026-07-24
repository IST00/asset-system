import { Navigate, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Spin } from 'antd'
import AssetAccessBoundary from '@/features/assets/AssetAccessBoundary'
import ProtectedRoute from './ProtectedRoute'

const Login = lazy(() => import('@/pages/Login'))
const Home = lazy(() => import('@/pages/Home'))
const Assets = lazy(() => import('@/pages/Assets'))
const AssetDetail = lazy(() => import('@/pages/AssetDetail'))
const AssetForm = lazy(() => import('@/pages/AssetForm'))
const NotFound = lazy(() => import('@/pages/NotFound'))
const AppShell = lazy(() => import('@/layouts/AppShell'))

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
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/home" replace />} />
          <Route path="home" element={<Home />} />
          <Route
            path="assets"
            element={
              <AssetAccessBoundary access="view">
                <Assets />
              </AssetAccessBoundary>
            }
          />
          <Route
            path="assets/new"
            element={
              <AssetAccessBoundary access="create">
                <AssetForm />
              </AssetAccessBoundary>
            }
          />
          <Route
            path="assets/:assetId"
            element={
              <AssetAccessBoundary access="view">
                <AssetDetail />
              </AssetAccessBoundary>
            }
          />
          <Route
            path="assets/:assetId/edit"
            element={
              <AssetAccessBoundary access="view">
                <AssetForm />
              </AssetAccessBoundary>
            }
          />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
