export interface NavigationEntry {
  key: string
  labelKey: string
  path: string
  icon: string
  mobile?: boolean
  mobilePermission?: string
  mobileUnlessPermission?: string
  permission?: string
  disabled?: boolean
}

export function filterNavigation(
  entries: NavigationEntry[],
  permissions: ReadonlySet<string>,
  mobileOnly = false,
): NavigationEntry[] {
  return entries.filter((entry) => {
    if (!mobileOnly) return !entry.permission || permissions.has(entry.permission)

    const mobileCapability =
      entry.mobilePermission === undefined || permissions.has(entry.mobilePermission)
    const mobileRestriction =
      entry.mobileUnlessPermission === undefined || !permissions.has(entry.mobileUnlessPermission)
    return mobileCapability && mobileRestriction && Boolean(entry.mobile)
  })
}
