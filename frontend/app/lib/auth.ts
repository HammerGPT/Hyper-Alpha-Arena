// Authentication configuration interface
interface AuthConfig {
  authProvider: string
  clientId: string
  appName: string
  organizationName: string
  redirectPath: string
}

export interface TokenResponse {
  access_token?: string
  token_type?: string
  refresh_token?: string
  id_token?: string
  expires_in?: number
  scope?: string
}

export interface ArenaSessionPayload {
  token: TokenResponse
  user: User
}

// User information interface
export interface User {
  owner: string
  name: string
  createdTime: string
  updatedTime: string
  id: string
  type: string
  displayName: string
  avatar: string
  email: string
  phone: string
  location: string
  address: string[]
  affiliation: string
  title: string
  homepage: string
  bio: string
  tag: string
  region: string
  language: string
  score: number
  isAdmin: boolean
  isGlobalAdmin: boolean
  isForbidden: boolean
  signupApplication: string
}

// Global auth configuration
let authConfig: AuthConfig | null = null

// Load authentication configuration
export async function loadAuthConfig(): Promise<AuthConfig | null> {
  if (authConfig) return authConfig

  try {
    const response = await fetch('/auth-config.json')
    if (!response.ok) {
      console.log('No auth config found, authentication disabled')
      return null
    }
    authConfig = await response.json()
    return authConfig
  } catch (error) {
    console.error('Failed to load auth config:', error)
    throw error
  }
}

// Generate random string
function generateRandomString(length: number): string {
  const charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
  let result = ''
  for (let i = 0; i < length; i++) {
    result += charset.charAt(Math.floor(Math.random() * charset.length))
  }
  return result
}

// Generate SHA256 hash
async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder()
  const data = encoder.encode(plain)
  return await crypto.subtle.digest('SHA-256', data)
}

// Convert ArrayBuffer to base64url
function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '')
}

// Generate PKCE parameters
async function generatePKCE() {
  const codeVerifier = generateRandomString(128)
  const codeChallenge = base64urlEncode(await sha256(codeVerifier))
  return {
    codeVerifier,
    codeChallenge,
    codeChallengeMethod: 'S256'
  }
}

// Get sign in URL
export async function getSignInUrl(): Promise<string | null> {
  const config = await loadAuthConfig()
  if (!config) return null

  if (typeof window === 'undefined') return null

  try {
    // Generate PKCE parameters
    const pkce = await generatePKCE()

    // Save code_verifier to localStorage (survives cross-domain redirects)
    localStorage.setItem('pkce_code_verifier', pkce.codeVerifier)
    console.log('Generated PKCE code_verifier:', pkce.codeVerifier.substring(0, 20) + '...')
    console.log('Generated PKCE code_challenge:', pkce.codeChallenge)

    // Generate random state
    const state = generateRandomString(32)
    localStorage.setItem('oauth_state', state)

    // Build arena relay redirect URI, include PKCE verifier + a state hint for server-side exchange
    const relayParams = new URLSearchParams({
      return_to: window.location.origin,
      code_verifier: pkce.codeVerifier,
      state_hint: state,
    })
    const redirectUri = `${config.authProvider}/arena-callback?${relayParams.toString()}`
    const params = new URLSearchParams({
      client_id: config.clientId,
      response_type: 'code',
      redirect_uri: redirectUri,
      scope: 'read',
      state: state,
      code_challenge: pkce.codeChallenge,
      code_challenge_method: pkce.codeChallengeMethod,
      prompt: 'select_account'  // Force account selection screen
    })

    return `${config.authProvider}/login/oauth/authorize?${params.toString()}`
  } catch (error) {
    console.error('Failed to generate sign in URL:', error)
    return null
  }
}

// Exchange authorization code for access token
export async function exchangeCodeForToken(code: string, state: string): Promise<string | null> {
  const config = await loadAuthConfig()
  if (!config) return null

  try {
    // Verify state parameter (skip if not found due to cross-domain issues)
    const savedState = localStorage.getItem('oauth_state')
    if (savedState && state !== savedState) {
      console.error('Invalid state parameter')
      return null
    }

    // Get code_verifier (generate new one if not found due to cross-domain issues)
    let codeVerifier = localStorage.getItem('pkce_code_verifier')
    console.log('Retrieved code_verifier from localStorage:', codeVerifier ? codeVerifier.substring(0, 20) + '...' : 'null')
    if (!codeVerifier) {
      console.warn('No code verifier found, using authorization code flow without PKCE')
      codeVerifier = '' // Use empty string for non-PKCE flow
    }

    // Clean up localStorage
    localStorage.removeItem('oauth_state')
    localStorage.removeItem('pkce_code_verifier')

    // Build token request
    const tokenUrl = `${config.authProvider}/api/login/oauth/access_token`
    const params = new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      code: code
    })

    // Add code_verifier for PKCE if available
    if (codeVerifier) {
      params.append('code_verifier', codeVerifier)
      console.log('Using PKCE flow with code_verifier')
    } else {
      console.log('Using standard flow without PKCE')
    }

    const response = await fetch(tokenUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    })

    if (!response.ok) {
      console.error('Failed to exchange code for token:', response.status, response.statusText)
      const errorText = await response.text()
      console.error('Error response:', errorText)
      return null
    }

    const data = await response.json()
    console.log('Token exchange response:', data)
    const accessToken = data.access_token || null
    console.log('Extracted access_token:', accessToken ? `${accessToken.substring(0, 10)}...` : 'null')

    // Debug: Try to decode JWT token to check its content
    if (accessToken) {
      try {
        const tokenParts = accessToken.split('.')
        if (tokenParts.length === 3) {
          // Add padding if needed for base64url decoding
          let payload = tokenParts[1]
          payload += '='.repeat((4 - payload.length % 4) % 4)
          // Replace base64url chars with base64 chars
          payload = payload.replace(/-/g, '+').replace(/_/g, '/')
          const decoded = JSON.parse(atob(payload))
          console.log('Token payload:', decoded)
          console.log('Token expires at:', new Date(decoded.exp * 1000))
          console.log('Token issued for:', decoded.aud)
        } else {
          console.log('Token format:', `${tokenParts.length} parts, not a standard JWT`)
        }
      } catch (e) {
        console.log('Token decode error:', e)
        console.log('Token length:', accessToken.length)
        console.log('Token starts with:', accessToken.substring(0, 50))
      }
    }

    return accessToken
  } catch (error) {
    console.error('Token exchange error:', error)
    return null
  }
}

// Helper function to decode base64url with UTF-8 support
function decodeBase64Url(input: string): string {
  // Replace base64url chars with base64 chars
  let base64 = input.replace(/-/g, '+').replace(/_/g, '/')
  // Add padding if needed
  base64 += '='.repeat((4 - base64.length % 4) % 4)

  // Decode base64 to binary string
  const binaryString = atob(base64)

  // Convert binary string to UTF-8
  // Modern browsers support TextDecoder
  if (typeof TextDecoder !== 'undefined') {
    const bytes = new Uint8Array(binaryString.length)
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }
    return new TextDecoder('utf-8').decode(bytes)
  } else {
    // Fallback for older browsers
    const bytes = []
    for (let i = 0; i < binaryString.length; i++) {
      bytes.push(binaryString.charCodeAt(i))
    }
    return decodeURIComponent(escape(String.fromCharCode(...bytes)))
  }
}

// Get user information
export async function getUserInfo(token: string): Promise<User | null> {
  console.log('Getting user info with token:', token ? `${token.substring(0, 10)}...` : 'null')

  try {
    // Decode JWT token to extract user information
    // JWT format: header.payload.signature
    const tokenParts = token.split('.')
    if (tokenParts.length !== 3) {
      console.error('Invalid JWT token format')
      return null
    }

    // Decode the payload (second part) with UTF-8 support
    const payloadString = decodeBase64Url(tokenParts[1])
    const decoded = JSON.parse(payloadString)
    console.log('[getUserInfo] Decoded token payload:', decoded)

    // Map JWT claims to User interface
    const user: User = {
      owner: decoded.owner || '',
      name: decoded.name || decoded.email || '',
      createdTime: decoded.createdTime || '',
      updatedTime: decoded.updatedTime || '',
      id: decoded.id || decoded.sub || '',
      type: decoded.type || 'normal-user',
      displayName: decoded.displayName || decoded.name || '',
      avatar: decoded.avatar || '',
      email: decoded.email || '',
      phone: decoded.phone || '',
      location: decoded.location || '',
      address: decoded.address || [],
      affiliation: decoded.affiliation || '',
      title: decoded.title || '',
      homepage: decoded.homepage || '',
      bio: decoded.bio || '',
      tag: decoded.tag || '',
      region: decoded.region || '',
      language: decoded.language || '',
      score: decoded.score || 0,
      isAdmin: decoded.isAdmin || false,
      isGlobalAdmin: decoded.isGlobalAdmin || false,
      isForbidden: decoded.isForbidden || false,
      signupApplication: decoded.signupApplication || ''
    }

    console.log('[getUserInfo] Extracted user info:', user)
    return user
  } catch (error) {
    console.error('Failed to decode user info from token:', error)
    return null
  }
}

export function decodeArenaSession(session: string): ArenaSessionPayload | null {
  try {
    const decoded = decodeBase64Url(session)
    const payload = JSON.parse(decoded)
    if (!payload?.token?.access_token || !payload?.user) {
      throw new Error('Incomplete session payload')
    }
    return payload
  } catch (error) {
    console.error('Failed to decode arena session payload:', error)
    return null
  }
}

// Get sign out URL (deprecated - use ssoLogout instead)
export async function getSignOutUrl(): Promise<string | null> {
  const config = await loadAuthConfig()
  if (!config) return null

  if (typeof window === 'undefined') return null

  const redirectUri = window.location.origin
  return `${config.authProvider}/logout?redirect_uri=${encodeURIComponent(redirectUri)}`
}

// SSO Logout - Clear Casdoor session across all apps
export async function ssoLogout(token: string): Promise<boolean> {
  const config = await loadAuthConfig()
  if (!config) {
    console.warn('No auth config, skipping SSO logout')
    return false
  }

  try {
    const response = await fetch(`${config.authProvider}/api/sso-logout`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      credentials: 'include'
    })

    if (!response.ok) {
      console.error('SSO logout failed:', response.status, response.statusText)
      return false
    }

    console.log('SSO logout successful')
    return true
  } catch (error) {
    console.error('SSO logout error:', error)
    return false
  }
}
