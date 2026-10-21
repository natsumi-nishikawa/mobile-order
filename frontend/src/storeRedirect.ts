const STAFF_PATHS = new Set(['/staff', '/staff/orders', '/staff/tables'])
const ADMIN_PATHS = new Set([
  '/admin',
  '/admin/products',
  '/admin/categories',
  '/admin/tables',
  '/admin/business-hours',
  '/admin/accounting',
  '/admin/staff-users',
])

function isAllowedStorePath(path: string) {
  return STAFF_PATHS.has(path)
    || ADMIN_PATHS.has(path)
    || /^\/staff\/accounting\/[1-9][0-9]*$/.test(path)
    || /^\/admin\/accounting\/[1-9][0-9]*$/.test(path)
}

export function defaultStorePath(groups: readonly string[] = []) {
  return groups.includes('admin') ? '/admin' : '/staff'
}

export function safeStoreReturnPath(
  candidate: string | null | undefined,
  groups?: readonly string[],
) {
  const fallback = defaultStorePath(groups)
  if (
    !candidate
    || candidate !== candidate.trim()
    || candidate.includes('\\')
    || candidate.includes('%')
    || candidate.includes('?')
    || candidate.includes('#')
    || candidate.startsWith('//')
    || !isAllowedStorePath(candidate)
  ) {
    return fallback
  }

  if (groups) {
    if (candidate.startsWith('/admin') && !groups.includes('admin')) return fallback
    if (
      candidate.startsWith('/staff')
      && !groups.some((group) => group === 'staff' || group === 'admin')
    ) return fallback
  }
  return candidate
}
