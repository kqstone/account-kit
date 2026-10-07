import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react'
import type { AccountUser, TokenPair } from '@kqstone/account-ui-react'
import { accountClient, tokenStore } from '../lib/auth'
import { getSetupStatus } from '../lib/api'
import type { SetupStatusResponse } from '../types'

interface AuthContextType {
  initialized: boolean | null
  setupStatus: SetupStatusResponse | null
  checkSetupStatus: () => Promise<boolean>
  setInitialized: (init: boolean) => void
  user: AccountUser | null
  token: string | null
  loadingUser: boolean
  refreshUser: () => Promise<void>
  logout: (allDevices?: boolean) => Promise<void>
  outboxDrawerOpen: boolean
  setOutboxDrawerOpen: (open: boolean) => void
  toggleOutboxDrawer: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [initialized, setInitialized] = useState<boolean | null>(null)
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null)
  const [user, setUser] = useState<AccountUser | null>(null)
  const [token, setToken] = useState<string | null>(tokenStore.getAccessToken())
  const [loadingUser, setLoadingUser] = useState<boolean>(true)
  const [outboxDrawerOpen, setOutboxDrawerOpen] = useState<boolean>(false)

  const checkSetupStatus = useCallback(async (): Promise<boolean> => {
    try {
      const status = await getSetupStatus()
      setSetupStatus(status)
      setInitialized(status.initialized)
      return status.initialized
    } catch (err) {
      console.error('Failed to get setup status:', err)
      setInitialized(false)
      return false
    }
  }, [])

  const refreshUser = useCallback(async () => {
    const currentToken = tokenStore.getAccessToken()
    setToken(currentToken)
    if (!currentToken) {
      setUser(null)
      setLoadingUser(false)
      return
    }
    setLoadingUser(true)
    try {
      const u = await accountClient.me(currentToken)
      setUser(u)
    } catch (err) {
      console.warn('Failed to fetch /me:', err)
      setUser(null)
      // if 401 and refresh fails, tokenStore will clear
    } finally {
      setLoadingUser(false)
    }
  }, [])

  // Listen to tokenStore changes
  useEffect(() => {
    const unsub = tokenStore.subscribe((tokens: TokenPair | null) => {
      const nextAccessToken = tokens?.access_token || null
      setToken(nextAccessToken)
      if (!nextAccessToken) {
        setUser(null)
      } else {
        void refreshUser()
      }
    })
    return () => unsub()
  }, [refreshUser])

  // Initial load
  useEffect(() => {
    void checkSetupStatus().then((isInit) => {
      if (isInit && tokenStore.getAccessToken()) {
        void refreshUser()
      } else {
        setLoadingUser(false)
      }
    })
  }, [checkSetupStatus, refreshUser])

  const logout = useCallback(
    async (allDevices = false) => {
      const currentToken = tokenStore.getAccessToken()
      const currentRefreshToken = tokenStore.getRefreshToken()
      try {
        await accountClient.logout(currentToken, {
          refreshToken: currentRefreshToken,
          allDevices,
        })
      } catch (err) {
        console.warn('Logout error ignored:', err)
      } finally {
        tokenStore.clear()
        setUser(null)
        setToken(null)
      }
    },
    []
  )

  const toggleOutboxDrawer = useCallback(() => {
    setOutboxDrawerOpen((prev) => !prev)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        initialized,
        setupStatus,
        checkSetupStatus,
        setInitialized,
        user,
        token,
        loadingUser,
        refreshUser,
        logout,
        outboxDrawerOpen,
        setOutboxDrawerOpen,
        toggleOutboxDrawer,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
