function parseBaseUrl(
  value: string | undefined,
  protocols: readonly string[],
  label: string,
  production: boolean,
) {
  const candidate = value?.trim()
  if (!candidate) return ''
  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    throw new Error(`${label} must be an absolute URL`)
  }
  if (
    !protocols.includes(parsed.protocol)
    || parsed.username
    || parsed.password
    || parsed.pathname !== '/'
    || parsed.search
    || parsed.hash
  ) {
    throw new Error(`${label} is invalid`)
  }
  if (production && !['https:', 'wss:'].includes(parsed.protocol)) {
    throw new Error(`${label} must use a secure protocol in production`)
  }
  return parsed.origin
}

export function resolveApiOrigin(value: string | undefined, production: boolean) {
  return parseBaseUrl(value, ['http:', 'https:'], 'VITE_API_BASE_URL', production)
}

export function resolveWebSocketOrigin(
  value: string | undefined,
  production: boolean,
  pageLocation: Pick<Location, 'protocol' | 'host'>,
) {
  const configured = parseBaseUrl(value, ['ws:', 'wss:'], 'VITE_WS_BASE_URL', production)
  if (configured) return configured
  if (production && pageLocation.protocol !== 'https:') {
    throw new Error('Production WebSocket connections require an HTTPS page')
  }
  const protocol = pageLocation.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${pageLocation.host}`
}

export const API_ORIGIN = resolveApiOrigin(import.meta.env.VITE_API_BASE_URL, import.meta.env.PROD)
export const WS_ORIGIN = resolveWebSocketOrigin(
  import.meta.env.VITE_WS_BASE_URL,
  import.meta.env.PROD,
  window.location,
)
