// API configuration
const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? '/api' 
  : '/api'  // Use proxy, don't hardcode port

// Hardcoded user for paper trading (matches backend initialization)
const HARDCODED_USERNAME = 'default'

// Helper function for making API requests
export async function apiRequest(
  endpoint: string, 
  options: RequestInit = {}
): Promise<Response> {
  const url = `${API_BASE_URL}${endpoint}`
  
  const defaultOptions: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  }
  
  const response = await fetch(url, defaultOptions)
  
  if (!response.ok) {
    // Try to extract error message from response body
    try {
      const errorData = await response.json()
      const errorMessage = errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      throw new Error(errorMessage)
    } catch (e) {
      // If parsing fails, throw generic error
      throw new Error(`HTTP error! status: ${response.status}`)
    }
  }
  
  const contentType = response.headers.get('content-type')
  if (!contentType || !contentType.includes('application/json')) {
    throw new Error('Response is not JSON')
  }
  
  return response
}

// Specific API functions
export async function checkRequiredConfigs() {
  const response = await apiRequest('/config/check-required')
  return response.json()
}

// Crypto-specific API functions
export async function getCryptoSymbols() {
  const response = await apiRequest('/crypto/symbols')
  return response.json()
}

export async function getCryptoPrice(symbol: string) {
  const response = await apiRequest(`/crypto/price/${symbol}`)
  return response.json()
}

export async function getCryptoMarketStatus(symbol: string) {
  const response = await apiRequest(`/crypto/status/${symbol}`)
  return response.json()
}

export async function getPopularCryptos() {
  const response = await apiRequest('/crypto/popular')
  return response.json()
}

// AI Decision Log interfaces and functions
export interface AIDecision {
  id: number
  account_id: number
  decision_time: string
  reason: string
  operation: string
  symbol?: string
  prev_portion: number
  target_portion: number
  total_balance: number
  executed: string
  order_id?: number
}

export interface AIDecisionFilters {
  operation?: string
  symbol?: string
  executed?: boolean
  start_date?: string
  end_date?: string
  limit?: number
}

export async function getAIDecisions(accountId: number, filters?: AIDecisionFilters): Promise<AIDecision[]> {
  const params = new URLSearchParams()
  if (filters?.operation) params.append('operation', filters.operation)
  if (filters?.symbol) params.append('symbol', filters.symbol)
  if (filters?.executed !== undefined) params.append('executed', filters.executed.toString())
  if (filters?.start_date) params.append('start_date', filters.start_date)
  if (filters?.end_date) params.append('end_date', filters.end_date)
  if (filters?.limit) params.append('limit', filters.limit.toString())
  
  const queryString = params.toString()
  const endpoint = `/accounts/${accountId}/ai-decisions${queryString ? `?${queryString}` : ''}`
  
  const response = await apiRequest(endpoint)
  return response.json()
}

export async function getAIDecisionById(accountId: number, decisionId: number): Promise<AIDecision> {
  const response = await apiRequest(`/accounts/${accountId}/ai-decisions/${decisionId}`)
  return response.json()
}

export async function getAIDecisionStats(accountId: number, days?: number): Promise<{
  total_decisions: number
  executed_decisions: number
  execution_rate: number
  operations: { [key: string]: number }
  avg_target_portion: number
}> {
  const params = days ? `?days=${days}` : ''
  const response = await apiRequest(`/accounts/${accountId}/ai-decisions/stats${params}`)
  return response.json()
}

// User authentication interfaces
export interface User {
  id: number
  username: string
  email?: string
  is_active: boolean
}

export interface UserAuthResponse {
  user: User
  session_token: string
  expires_at: string
}

// Trading Account management functions
export interface TradingAccount {
  id: number
  user_id: number
  name: string  // Display name (e.g., "GPT Trader", "Claude Analyst")
  model?: string  // AI model (e.g., "gpt-4-turbo")
  base_url?: string  // API endpoint
  api_key?: string  // API key (masked in responses)
  initial_capital: number
  current_cash: number
  frozen_cash: number
  account_type: string  // "AI" or "MANUAL"
  is_active: boolean
  auto_trading_enabled?: boolean
}

export interface TradingAccountCreate {
  name: string
  model?: string
  base_url?: string
  api_key?: string
  initial_capital?: number
  account_type?: string
  auto_trading_enabled?: boolean
}

export interface TradingAccountUpdate {
  name?: string
  model?: string
  base_url?: string
  api_key?: string
  auto_trading_enabled?: boolean
}

export type StrategyTriggerMode = 'realtime' | 'interval' | 'tick_batch'

export interface StrategyConfig {
  trigger_mode: StrategyTriggerMode
  interval_seconds?: number | null
  tick_batch_size?: number | null
  enabled: boolean
  last_trigger_at?: string | null
}

export interface StrategyConfigUpdate {
  trigger_mode: StrategyTriggerMode
  interval_seconds?: number | null
  tick_batch_size?: number | null
  enabled: boolean
}


export async function loginUser(username: string, password: string): Promise<UserAuthResponse> {
  const response = await apiRequest('/users/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  return response.json()
}

export async function getUserProfile(sessionToken: string): Promise<User> {
  const response = await apiRequest(`/users/profile?session_token=${sessionToken}`)
  return response.json()
}

// Trading Account management functions (matching backend query parameter style)
export async function listTradingAccounts(sessionToken: string): Promise<TradingAccount[]> {
  const response = await apiRequest(`/accounts/?session_token=${sessionToken}`)
  return response.json()
}

export async function createTradingAccount(account: TradingAccountCreate, sessionToken: string): Promise<TradingAccount> {
  const response = await apiRequest(`/accounts/?session_token=${sessionToken}`, {
    method: 'POST',
    body: JSON.stringify(account),
  })
  return response.json()
}

export async function getAccountStrategy(accountId: number): Promise<StrategyConfig> {
  const response = await apiRequest(`/account/${accountId}/strategy`)
  return response.json()
}

export async function updateAccountStrategy(accountId: number, config: StrategyConfigUpdate): Promise<StrategyConfig> {
  const response = await apiRequest(`/account/${accountId}/strategy`, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
  return response.json()
}

export async function updateTradingAccount(accountId: number, account: TradingAccountUpdate, sessionToken: string): Promise<TradingAccount> {
  const response = await apiRequest(`/accounts/${accountId}?session_token=${sessionToken}`, {
    method: 'PUT',
    body: JSON.stringify(account),
  })
  return response.json()
}

export async function deleteTradingAccount(accountId: number, sessionToken: string): Promise<void> {
  await apiRequest(`/accounts/${accountId}?session_token=${sessionToken}`, {
    method: 'DELETE',
  })
}

// Account functions for paper trading with hardcoded user
// Note: Backend initializes default user on startup, frontend just queries the endpoints
export async function getAccounts(): Promise<TradingAccount[]> {
  const response = await apiRequest('/account/list')
  return response.json()
}

export async function getOverview(): Promise<any> {
  const response = await apiRequest('/account/overview')
  return response.json()
}

export async function createAccount(account: TradingAccountCreate): Promise<TradingAccount> {
  const response = await apiRequest('/account/', {
    method: 'POST',
    body: JSON.stringify({
      name: account.name,
      model: account.model,
      base_url: account.base_url,
      api_key: account.api_key,
      account_type: account.account_type || 'AI',
      initial_capital: account.initial_capital || 10000,
      auto_trading_enabled: account.auto_trading_enabled ?? true,
    })
  })
  return response.json()
}

export async function updateAccount(accountId: number, account: TradingAccountUpdate): Promise<TradingAccount> {
  const response = await apiRequest(`/account/${accountId}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: account.name,
      model: account.model,
      base_url: account.base_url,
      api_key: account.api_key,
      auto_trading_enabled: account.auto_trading_enabled,
    })
  })
  return response.json()
}

export async function testLLMConnection(testData: {
  model?: string;
  base_url?: string;
  api_key?: string;
}): Promise<{ success: boolean; message: string; response?: any }> {
  const response = await apiRequest('/account/test-llm', {
    method: 'POST',
    body: JSON.stringify(testData)
  })
  return response.json()
}

// Alpha Arena aggregated feeds
export interface ArenaAccountMeta {
  account_id: number
  name: string
  model?: string | null
}

export interface ArenaTrade {
  trade_id: number
  order_id?: number | null
  order_no?: string | null
  account_id: number
  account_name: string
  model?: string | null
  side: string
  direction: string
  symbol: string
  market: string
  price: number
  quantity: number
  notional: number
  commission: number
  trade_time?: string | null
}

export interface ArenaTradesResponse {
  generated_at: string
  accounts: ArenaAccountMeta[]
  trades: ArenaTrade[]
}

export async function getArenaTrades(params?: { limit?: number; account_id?: number }): Promise<ArenaTradesResponse> {
  const search = new URLSearchParams()
  if (params?.limit) search.append('limit', params.limit.toString())
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  const query = search.toString()
  const response = await apiRequest(`/arena/trades${query ? `?${query}` : ''}`)
  return response.json()
}

export interface ArenaModelChatEntry {
  id: number
  account_id: number
  account_name: string
  model?: string | null
  operation: string
  symbol?: string | null
  reason: string
  executed: boolean
  prev_portion: number
  target_portion: number
  total_balance: number
  order_id?: number | null
  decision_time?: string | null
  trigger_mode?: StrategyTriggerMode | null
  strategy_enabled?: boolean
  last_trigger_at?: string | null
  trigger_latency_seconds?: number | null
  prompt_snapshot?: string | null
  reasoning_snapshot?: string | null
  decision_snapshot?: string | null
}

export interface ArenaModelChatResponse {
  generated_at: string
  entries: ArenaModelChatEntry[]
}

export async function getArenaModelChat(params?: { limit?: number; account_id?: number }): Promise<ArenaModelChatResponse> {
  const search = new URLSearchParams()
  if (params?.limit) search.append('limit', params.limit.toString())
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  const query = search.toString()
  const response = await apiRequest(`/arena/model-chat${query ? `?${query}` : ''}`)
  return response.json()
}

export interface ArenaPositionItem {
  id: number
  symbol: string
  name: string
  market: string
  side: string
  quantity: number
  avg_cost: number
  current_price: number
  notional: number
  current_value: number
  unrealized_pnl: number
}

export interface ArenaPositionsAccount {
  account_id: number
  account_name: string
  model?: string | null
  total_unrealized_pnl: number
  available_cash: number
  positions: ArenaPositionItem[]
  total_assets: number
  initial_capital: number
  total_return?: number | null
}

export interface ArenaPositionsResponse {
  generated_at: string
  accounts: ArenaPositionsAccount[]
}

export async function getArenaPositions(params?: { account_id?: number }): Promise<ArenaPositionsResponse> {
  const search = new URLSearchParams()
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  const query = search.toString()
  const response = await apiRequest(`/arena/positions${query ? `?${query}` : ''}`)
  return response.json()
}

export interface ArenaAnalyticsAccount {
  account_id: number
  account_name: string
  model?: string | null
  initial_capital: number
  current_cash: number
  positions_value: number
  total_assets: number
  total_pnl: number
  total_return_pct?: number | null
  total_fees: number
  trade_count: number
  total_volume: number
  first_trade_time?: string | null
  last_trade_time?: string | null
  biggest_gain: number
  biggest_loss: number
  win_rate?: number | null
  loss_rate?: number | null
  sharpe_ratio?: number | null
  balance_volatility: number
  decision_count: number
  executed_decisions: number
  decision_execution_rate?: number | null
  avg_target_portion?: number | null
  avg_decision_interval_minutes?: number | null
}

export interface ArenaAnalyticsSummary {
  total_assets: number
  total_pnl: number
  total_return_pct?: number | null
  total_fees: number
  total_volume: number
  average_sharpe_ratio?: number | null
}

export interface ArenaAnalyticsResponse {
  generated_at: string
  accounts: ArenaAnalyticsAccount[]
  summary: ArenaAnalyticsSummary
}

export async function getArenaAnalytics(params?: { account_id?: number }): Promise<ArenaAnalyticsResponse> {
  const search = new URLSearchParams()
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  const query = search.toString()
  const response = await apiRequest(`/arena/analytics${query ? `?${query}` : ''}`)
  return response.json()
}

// Legacy aliases for backward compatibility
export type AIAccount = TradingAccount
export type AIAccountCreate = TradingAccountCreate

// Updated legacy functions to use default mode for simulation
export const listAIAccounts = () => getAccounts()
export const createAIAccount = (account: any) => {
  console.warn("createAIAccount is deprecated. Use default mode or new trading account APIs.")
  return Promise.resolve({} as TradingAccount)
}
export const updateAIAccount = (id: number, account: any) => {
  console.warn("updateAIAccount is deprecated. Use default mode or new trading account APIs.")
  return Promise.resolve({} as TradingAccount)
}
export const deleteAIAccount = (id: number) => {
  console.warn("deleteAIAccount is deprecated. Use default mode or new trading account APIs.")
  return Promise.resolve()
}
