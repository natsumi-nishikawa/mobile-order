export const DEMO_CSRF_KEY = 'demo_csrf_token'

type DemoCsrfStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export class DemoSessionUnavailableError extends Error {}

export function readDemoCsrfToken(storage: Pick<Storage, 'getItem'> = sessionStorage) {
  return storage.getItem(DEMO_CSRF_KEY)
}

export function saveDemoCsrfToken(token: string, storage: Pick<Storage, 'setItem'> = sessionStorage) {
  if (!token) throw new Error('デモ認証情報を保存できません')
  storage.setItem(DEMO_CSRF_KEY, token)
}

export function clearDemoCsrfToken(storage: Pick<Storage, 'removeItem'> = sessionStorage) {
  storage.removeItem(DEMO_CSRF_KEY)
}

export async function requireDemoCsrfToken(
  restore: () => Promise<boolean>,
  storage: DemoCsrfStorage = sessionStorage,
) {
  const current = readDemoCsrfToken(storage)
  if (current) return current

  const authenticated = await restore()
  const restored = readDemoCsrfToken(storage)
  if (!authenticated || !restored) {
    throw new DemoSessionUnavailableError('デモ認証を確認できません。再ログインしてください。')
  }
  return restored
}
