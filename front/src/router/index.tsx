import { Navigate, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Spin } from 'antd'
import AssetAccessBoundary from '@/features/assets/AssetAccessBoundary'
import PermissionBoundary from './PermissionBoundary'
import ProtectedRoute from './ProtectedRoute'

const Login = lazy(() => import('@/pages/Login'))
const FeishuCallback = lazy(() => import('@/pages/FeishuCallback'))
const Home = lazy(() => import('@/pages/Home'))
const Assets = lazy(() => import('@/pages/Assets'))
const AssetDetail = lazy(() => import('@/pages/AssetDetail'))
const AssetForm = lazy(() => import('@/pages/AssetForm'))
const Workflows = lazy(() => import('@/pages/Workflows'))
const Inventory = lazy(() => import('@/pages/Inventory'))
const Approvals = lazy(() => import('@/pages/Approvals'))
const Imports = lazy(() => import('@/pages/Imports'))
const MasterData = lazy(() => import('@/pages/MasterData'))
const Permissions = lazy(() => import('@/pages/Permissions'))
const AuditLogs = lazy(() => import('@/pages/AuditLogs'))
const Profile = lazy(() => import('@/pages/Profile'))
const Notifications = lazy(() => import('@/pages/Notifications'))
const AssetScan = lazy(() => import('@/pages/AssetScan'))
const AssetScanUse = lazy(() => import('@/pages/AssetScanUse'))
const Settings = lazy(() => import('@/pages/Settings'))
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
        <Route path="/feishu/callback" element={<FeishuCallback />} />
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
          <Route path="workflows" element={<Workflows />} />
          <Route path="inventory" element={<Inventory />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="imports" element={<Imports />} />
          <Route path="master-data" element={<MasterData />} />
          <Route path="permissions" element={<Permissions />} />
          <Route path="logs" element={<AuditLogs />} />
          <Route path="profile" element={<Profile />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="scan" element={<AssetScan />} />
          <Route
            path="scan-use"
            element={
              <AssetAccessBoundary access="view">
                <AssetScanUse />
              </AssetAccessBoundary>
            }
          />
          <Route
            path="settings"
            element={
              <PermissionBoundary permission="system:user:view">
                <Settings />
              </PermissionBoundary>
            }
          />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
