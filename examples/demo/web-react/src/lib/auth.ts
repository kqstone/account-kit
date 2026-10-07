import {
  createAccountClient,
  createTokenStore,
  type AccountClient,
  type TokenStore,
} from '@kqstone/account-ui-react'

export const tokenStore: TokenStore = createTokenStore('account-kit:tokens')

export const accountClient: AccountClient = createAccountClient('/api/auth', {
  getToken: tokenStore.getAccessToken,
  logoutPath: '/logout',
  autoRefresh: {
    getRefreshToken: tokenStore.getRefreshToken,
    onTokens: tokenStore.set,
    onRefreshFailed: tokenStore.clear,
  },
})
