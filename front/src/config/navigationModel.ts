export interface NavigationEntry {
  key: string
  labelKey: string
  path: string
  icon: string
  mobile?: boolean
  permission?: string
  disabled?: boolean
}

export function filterNavigation(
  entries: NavigationEntry[],
  permissions: ReadonlySet<string>,
  mobileOnly = false,
): NavigationEntry[] {
  return entries.filter((entry) => {
    if (mobileOnly && !entry.mobile) return false
    return !entry.permission || permissions.has(entry.permission)
  })
}
