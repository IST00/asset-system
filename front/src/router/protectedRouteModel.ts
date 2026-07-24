export function canAccessProtectedRoute(token: string | null): boolean {
  return Boolean(token)
}
