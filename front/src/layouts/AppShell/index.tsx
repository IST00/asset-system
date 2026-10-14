import { Avatar, Button, Drawer, Dropdown, Tooltip } from 'antd'
import type { MenuProps } from 'antd'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeftRight,
  Bell,
  Box,
  ClipboardCheck,
  Database,
  FileUp,
  Home,
  LogOut,
  Menu,
  Package,
  ScanLine,
  ScrollText,
  Settings,
  ShieldCheck,
  UserRound,
  Workflow,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '@/api'
import { navigationEntries } from '@/config/navigation'
import { filterNavigation } from '@/config/navigationModel'
import type { NavigationEntry } from '@/config/navigationModel'
import { useAuthStore } from '@/store/auth'
import { roleCodeLabel } from '@/utils/displayLabels'
import './AppShell.css'

const iconMap: Record<string, LucideIcon> = {
  approval: ClipboardCheck,
  assets: Package,
  database: Database,
  home: Home,
  import: FileUp,
  logs: ScrollText,
  package: Package,
  scan: ScanLine,
  shield: ShieldCheck,
  user: UserRound,
  workflow: Workflow,
  workflows: ArrowLeftRight,
}

function NavigationIcon({ name, size = 20 }: { name: string; size?: number }) {
  const Icon = iconMap[name] ?? Box
  return <Icon aria-hidden="true" size={size} strokeWidth={1.8} />
}

export default function AppShell() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const { token, user, setUser, logout } = useAuthStore()
  const [drawerOpen, setDrawerOpen] = useState(false)

  useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const currentUser = await authApi.me()
      setUser(currentUser)
      return currentUser
    },
    enabled: Boolean(token),
    staleTime: 5 * 60 * 1000,
  })

  const permissions = useMemo(() => new Set(user?.permissions ?? []), [user?.permissions])
  const canViewSettings = permissions.has('system:user:view')
  const visibleEntries = useMemo(
    () => filterNavigation(navigationEntries, permissions),
    [permissions],
  )
  const desktopEntries = visibleEntries.filter((entry) => entry.key !== 'profile')
  const mobileEntries = filterNavigation(navigationEntries, permissions, true)
  const drawerEntries = visibleEntries.filter((entry) => !entry.mobile)

  const isSelected = (entry: NavigationEntry) =>
    entry.path === '/home'
      ? location.pathname === entry.path
      : location.pathname.startsWith(entry.path)

  const handleNavigation = (entry: NavigationEntry) => {
    if (entry.disabled) return
    navigate(entry.path)
    setDrawerOpen(false)
  }

  const handleLogout = () => {
    void authApi.logout().finally(() => {
      logout()
      navigate('/login')
    })
  }

  const accountMenu: MenuProps = {
    items: [
      {
        key: 'profile',
        icon: <UserRound aria-hidden="true" size={16} />,
        label: t('nav.profile'),
        onClick: () => navigate('/profile'),
      },
      {
        type: 'divider',
      },
      {
        key: 'logout',
        icon: <LogOut aria-hidden="true" size={16} />,
        label: t('nav.logout'),
        onClick: handleLogout,
      },
    ],
  }

  const renderRailItem = (entry: NavigationEntry) => {
    const label = t(entry.labelKey)
    const classNames = [
      'asset-shell__rail-button',
      isSelected(entry) ? 'asset-shell__rail-button--active' : '',
      entry.disabled ? 'asset-shell__rail-button--disabled' : '',
    ]
      .filter(Boolean)
      .join(' ')

    return (
      <Tooltip
        key={entry.key}
        title={entry.disabled ? `${label} · ${t('common.comingSoon')}` : label}
        placement="right"
        mouseEnterDelay={0.35}
        mouseLeaveDelay={0}
        arrow={false}
        classNames={{ root: 'asset-shell__rail-tooltip' }}
      >
        <button
          type="button"
          className={classNames}
          aria-label={label}
          aria-current={isSelected(entry) ? 'page' : undefined}
          aria-disabled={entry.disabled || undefined}
          onClick={() => handleNavigation(entry)}
        >
          <NavigationIcon name={entry.icon} />
        </button>
      </Tooltip>
    )
  }

  return (
    <div className="asset-shell">
      <aside className="asset-shell__rail" aria-label={t('app.name')}>
        <button
          type="button"
          className="asset-shell__brand"
          aria-label={t('nav.home')}
          onClick={() => navigate('/home')}
        >
          <Box aria-hidden="true" size={24} strokeWidth={2} />
        </button>

        <nav className="asset-shell__rail-nav" aria-label={t('app.name')}>
          {desktopEntries.map(renderRailItem)}
        </nav>

        <div className="asset-shell__rail-footer">
          {canViewSettings ? (
            <Tooltip
              title={t('nav.settings')}
              placement="right"
              mouseEnterDelay={0.35}
              mouseLeaveDelay={0}
              arrow={false}
              classNames={{ root: 'asset-shell__rail-tooltip' }}
            >
              <button
                type="button"
                className={
                  location.pathname.startsWith('/settings')
                    ? 'asset-shell__rail-button asset-shell__rail-button--active'
                    : 'asset-shell__rail-button'
                }
                aria-label={t('nav.settings')}
                aria-current={location.pathname.startsWith('/settings') ? 'page' : undefined}
                onClick={() => navigate('/settings')}
              >
                <Settings aria-hidden="true" size={20} strokeWidth={1.8} />
              </button>
            </Tooltip>
          ) : null}
          <Dropdown menu={accountMenu} placement="topLeft" trigger={['click']}>
            <button
              type="button"
              className="asset-shell__account-button"
              aria-label={t('nav.profile')}
            >
              <Avatar size={34}>{(user?.nickname || user?.username || 'A').slice(0, 1)}</Avatar>
            </button>
          </Dropdown>
        </div>
      </aside>

      <div className="asset-shell__workspace">
        <header className="asset-shell__topbar">
          <div className="asset-shell__mobile-brand">
            <Box aria-hidden="true" size={22} strokeWidth={2} />
            <span>{t('app.shortName')}</span>
          </div>
          <div className="asset-shell__topbar-actions">
            <Tooltip title={t('common.notifications')}>
              <Button
                type="text"
                shape="circle"
                aria-label={t('common.notifications')}
                icon={<Bell size={19} />}
                onClick={() => navigate('/notifications')}
              />
            </Tooltip>
            <Dropdown menu={accountMenu} placement="bottomRight" trigger={['click']}>
              <Button type="text" className="asset-shell__user-button">
                <Avatar size={30}>{(user?.nickname || user?.username || 'A').slice(0, 1)}</Avatar>
                <span>{user?.nickname || user?.username || 'admin'}</span>
              </Button>
            </Dropdown>
            <Button
              type="text"
              shape="circle"
              className="asset-shell__more-button"
              aria-label={t('common.more')}
              icon={<Menu size={20} />}
              onClick={() => setDrawerOpen(true)}
            />
          </div>
        </header>

        <main className="asset-shell__content">
          <div className="asset-shell__content-inner">
            <Outlet />
          </div>
        </main>
      </div>

      <nav className="asset-shell__mobile-nav" aria-label={t('app.name')}>
        {mobileEntries.map((entry) => {
          const active = isSelected(entry)
          return (
            <button
              key={entry.key}
              type="button"
              className={
                active ? 'asset-shell__mobile-nav-item is-active' : 'asset-shell__mobile-nav-item'
              }
              aria-current={active ? 'page' : undefined}
              aria-disabled={entry.disabled || undefined}
              onClick={() => handleNavigation(entry)}
            >
              <NavigationIcon name={entry.icon} size={19} />
              <span>{t(entry.labelKey)}</span>
            </button>
          )
        })}
      </nav>

      <Drawer
        title={t('app.name')}
        placement="right"
        width={320}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <div className="asset-shell__drawer-user">
          <Avatar size={44}>{(user?.nickname || user?.username || 'A').slice(0, 1)}</Avatar>
          <div>
            <strong>{user?.nickname || user?.username || 'admin'}</strong>
            <span>
              {user?.role || user?.roles?.[0]
                ? roleCodeLabel(user.role ?? user.roles?.[0])
                : t('nav.profile')}
            </span>
          </div>
        </div>
        <div className="asset-shell__drawer-nav">
          {drawerEntries.map((entry) => (
            <button
              key={entry.key}
              type="button"
              aria-disabled={entry.disabled || undefined}
              onClick={() => handleNavigation(entry)}
            >
              <NavigationIcon name={entry.icon} size={18} />
              <span>{t(entry.labelKey)}</span>
              {entry.disabled ? <small>{t('common.comingSoon')}</small> : null}
            </button>
          ))}
          {canViewSettings ? (
            <button
              type="button"
              onClick={() => {
                navigate('/settings')
                setDrawerOpen(false)
              }}
            >
              <Settings aria-hidden="true" size={18} />
              <span>{t('nav.settings')}</span>
            </button>
          ) : null}
        </div>
        <button type="button" className="asset-shell__drawer-logout" onClick={handleLogout}>
          <LogOut aria-hidden="true" size={18} />
          <span>{t('nav.logout')}</span>
        </button>
      </Drawer>
    </div>
  )
}
