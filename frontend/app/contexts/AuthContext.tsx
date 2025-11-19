'use client'

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import Cookies from 'js-cookie'
import { getUserInfo, loadAuthConfig, type User } from '@/lib/auth'
import { getMembershipInfo, type MembershipInfo } from '@/lib/api'

interface AuthContextType {
  user: User | null
  loading: boolean
  authEnabled: boolean
  membership: MembershipInfo | null
  membershipLoading: boolean
  setUser: (user: User | null) => void
  logout: () => void
  refreshMembership: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)
  const [membership, setMembership] = useState<MembershipInfo | null>(null)
  const [membershipLoading, setMembershipLoading] = useState(false)

  // Function to refresh membership data
  const refreshMembership = async () => {
    if (!authEnabled || !user) {
      setMembership(null)
      return
    }

    setMembershipLoading(true)
    try {
      const result = await getMembershipInfo()
      setMembership(result.membership)
    } catch (error) {
      console.error('Failed to refresh membership:', error)
      setMembership(null)
    } finally {
      setMembershipLoading(false)
    }
  }

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

  // Fetch membership info when user is authenticated
  useEffect(() => {
    if (!loading && user && authEnabled) {
      refreshMembership()
    }
  }, [user, loading, authEnabled])

  const logout = () => {
    // Local logout only: clear Arena cookies and state
    // Casdoor session remains active, but next login will show account selection
    // because we use prompt=select_account in getSignInUrl()
    Cookies.remove('arena_token')
    Cookies.remove('arena_user')
    setUser(null)
    setMembership(null)

    // Refresh page to show logged-out state
    window.location.href = '/'
  }

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      authEnabled,
      membership,
      membershipLoading,
      setUser,
      logout,
      refreshMembership
    }}>
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