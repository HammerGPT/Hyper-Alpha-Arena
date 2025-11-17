'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { decodeArenaSession, exchangeCodeForToken, getUserInfo } from '@/lib/auth'
import { useAuth } from '@/contexts/AuthContext'
import Cookies from 'js-cookie'

function CallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { setUser } = useAuth()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // New simplified flow: receive token directly from account.akooi.com
        const tokenParam = searchParams.get('token')
        console.log('[Callback] Token param:', tokenParam ? `${tokenParam.substring(0, 20)}...` : 'null')

        if (tokenParam) {
          console.log('[Callback] Received token from relay server, length:', tokenParam.length)

          // Fetch user info with the token
          console.log('[Callback] Fetching user info...')
          const userData = await getUserInfo(tokenParam)
          console.log('[Callback] User data received:', userData ? 'YES' : 'NO')

          if (!userData) {
            console.error('[Callback] Failed to get user information')
            setError('Failed to get user information')
            return
          }

          // Save token and user data
          console.log('[Callback] Saving token and user data to cookies...')
          Cookies.set('arena_token', tokenParam, { expires: 7 })
          Cookies.set('arena_user', JSON.stringify(userData), { expires: 7 })
          console.log('[Callback] Setting user in context:', userData.name)
          setUser(userData)
          console.log('[Callback] Redirecting to home...')
          router.push('/')
          return
        }

        // Legacy fallback: session payload (for backward compatibility)
        const sessionParam = searchParams.get('session')
        if (sessionParam) {
          const session = decodeArenaSession(sessionParam)
          if (!session) {
            setError('Invalid session payload received')
            return
          }

          const accessToken = session.token.access_token
          if (!accessToken) {
            setError('Missing access token in session payload')
            return
          }

          Cookies.set('arena_token', accessToken, { expires: 7 })
          Cookies.set('arena_user', JSON.stringify(session.user), { expires: 7 })
          setUser(session.user)
          router.push('/')
          return
        }

        // No valid parameters found
        setError('No authentication data received')
      } catch (err) {
        console.error('Callback error:', err)
        setError('Authentication failed. Please try again.')
      }
    }

    handleCallback()
  }, [searchParams, router, setUser])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="max-w-md w-full mx-auto p-6">
          <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-6 text-center">
            <h2 className="text-xl font-semibold text-destructive mb-2">
              Authentication Error
            </h2>
            <p className="text-muted-foreground mb-4">{error}</p>
            <button
              onClick={() => router.push('/')}
              className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none ring-offset-background bg-primary text-primary-foreground hover:bg-primary/90 h-10 py-2 px-4"
            >
              Go Back Home
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="max-w-md w-full mx-auto p-6 text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
        <h2 className="text-xl font-semibold text-foreground mb-2">
          Authenticating...
        </h2>
        <p className="text-muted-foreground">
          Please wait while we log you in
        </p>
      </div>
    </div>
  )
}

export default function CallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-background">
          <div className="max-w-md w-full mx-auto p-6 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Loading...
            </h2>
          </div>
        </div>
      }
    >
      <CallbackContent />
    </Suspense>
  )
}
