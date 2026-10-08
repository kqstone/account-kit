import {
  createAccountClient,
  createTokenStore,
  type AccountClient,
  type TokenStore,
} from '@kqstone/account-ui-react'
import { readDemoLocale } from './i18n'

export const tokenStore: TokenStore = createTokenStore('account-kit:tokens')

export const accountClient: AccountClient = createAccountClient('/api/auth', {
  getToken: tokenStore.getAccessToken,
  getLocale: readDemoLocale,
  logoutPath: '/logout',
  autoRefresh: {
    getRefreshToken: tokenStore.getRefreshToken,
    onTokens: tokenStore.set,
    onRefreshFailed: tokenStore.clear,
  },
})
