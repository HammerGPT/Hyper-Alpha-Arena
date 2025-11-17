'use client'

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import Cookies from 'js-cookie'
import { getUserInfo, loadAuthConfig, type User } from '@/lib/auth'

interface AuthContextType {
  user: User | null
  loading: boolean
  authEnabled: boolean
  setUser: (user: User | null) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)

  useEffect(() => {
    const initAuth = async () => {
      try {
        // Check if auth is configured
        const config = await loadAuthConfig()
        const isAuthEnabled = !!config
        setAuthEnabled(isAuthEnabled)

        if (!isAuthEnabled) {
          // Auth disabled, skip authentication
          setLoading(false)
          return
        }

        // Try to load user from cache first
        const cachedUser = Cookies.get('arena_user')
        if (cachedUser) {
          try {
            setUser(JSON.parse(cachedUser))
          } catch (e) {
            console.error('Failed to parse cached user:', e)
          }
        }

        // Try to refresh user info with token
        const token = Cookies.get('arena_token')
        if (token) {
          const userData = await getUserInfo(token)
          if (userData) {
            setUser(userData)
            // Update cache
            Cookies.set('arena_user', JSON.stringify(userData), { expires: 7 })
          } else {
            // Token invalid, clear cache
            Cookies.remove('arena_token')
            Cookies.remove('arena_user')
            setUser(null)
          }
        }
      } catch (error) {
        console.error('Auth initialization error:', error)
      } finally {
        setLoading(false)
      }
    }

    initAuth()
  }, [])

  const logout = () => {
    // Local logout only: clear Arena cookies and state
    // Casdoor session remains active, but next login will show account selection
    // because we use prompt=select_account in getSignInUrl()
    Cookies.remove('arena_token')
    Cookies.remove('arena_user')
    setUser(null)

    // Refresh page to show logged-out state
    window.location.href = '/'
  }

  return (
    <AuthContext.Provider value={{ user, loading, authEnabled, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}