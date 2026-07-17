import Cookies from 'js-cookie'

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
  wallet_address?: string | null  // Hyperliquid mainnet wallet address
  has_mainnet_wallet?: boolean  // Whether account has mainnet wallet configured
  show_on_dashboard?: boolean  // Whether to show on Dashboard views
  avatar_preset_id?: number | null  // Arena View pixel character preset (1-12)
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
  exchange?: string  // "hyperliquid" or "binance"
  // Response-only: account-level auto-trading pause switch (separate from the
  // per-strategy `enabled` flag). Never send this back on PUT.
  auto_trading_enabled?: boolean
}

export interface StrategyConfigUpdate {
  trigger_mode: StrategyTriggerMode
  interval_seconds?: number | null
  tick_batch_size?: number | null
  enabled: boolean
}

// Prompt templates & bindings
export interface PromptTemplate {
  id: number
  key: string
  name: string
  description?: string | null
  templateText: string
  systemTemplateText: string
  isSystem: string
  isDeleted: string
  createdBy: string
  updatedBy?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

export interface PromptBinding {
  id: number
  accountId: number
  accountName: string
  accountModel?: string | null
  promptTemplateId: number
  promptKey: string
  promptName: string
  updatedBy?: string | null
  updatedAt?: string | null
}

export interface PromptListResponse {
  templates: PromptTemplate[]
  bindings: PromptBinding[]
}

export interface PromptTemplateUpdateRequest {
  templateText: string
  description?: string
  updatedBy?: string
}

export interface PromptTemplateCreateRequest {
  name: string
  description?: string
  templateText?: string
  createdBy?: string
}

export interface PromptTemplateCopyRequest {
  newName?: string
  createdBy?: string
}

export interface PromptTemplateNameUpdateRequest {
  name: string
  description?: string
  updatedBy?: string
}

export interface PromptBindingUpsertRequest {
  id?: number
  accountId: number
  promptTemplateId: number
  updatedBy?: string
}

export async function getPromptTemplates(): Promise<PromptListResponse> {
  const response = await apiRequest('/prompts')
  return response.json()
}

export async function updatePromptTemplate(
  key: string,
  payload: PromptTemplateUpdateRequest,
): Promise<PromptTemplate> {
  const response = await apiRequest(`/prompts/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function createPromptTemplate(
  payload: PromptTemplateCreateRequest,
): Promise<PromptTemplate> {
  const response = await apiRequest('/prompts', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function copyPromptTemplate(
  templateId: number,
  payload: PromptTemplateCopyRequest,
): Promise<PromptTemplate> {
  const response = await apiRequest(`/prompts/${templateId}/copy`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function deletePromptTemplate(templateId: number): Promise<void> {
  await apiRequest(`/prompts/${templateId}`, {
    method: 'DELETE',
  })
}

export async function updatePromptTemplateName(
  templateId: number,
  payload: PromptTemplateNameUpdateRequest,
): Promise<PromptTemplate> {
  const response = await apiRequest(`/prompts/${templateId}/name`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function upsertPromptBinding(
  payload: PromptBindingUpsertRequest,
): Promise<PromptBinding> {
  const response = await apiRequest('/prompts/bindings', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function deletePromptBinding(bindingId: number): Promise<void> {
  await apiRequest(`/prompts/bindings/${bindingId}`, {
    method: 'DELETE',
  })
}

export interface VariablesReferenceResponse {
  content: string
}

export async function getVariablesReference(lang: string = 'en'): Promise<VariablesReferenceResponse> {
  const response = await apiRequest(`/prompts/variables-reference?lang=${lang}`)
  return response.json()
}

export interface PromptPreviewRequest {
  templateText?: string  // Optional: Use this template text directly (for preview before save)
  promptTemplateKey?: string  // Optional: Fallback to database template if templateText not provided
  accountIds: number[]
  symbols?: string[]
  exchanges?: string[]  // Optional: Array of exchanges ["hyperliquid", "binance"] (default: ["hyperliquid"])
}

export interface PromptPreviewItem {
  accountId: number
  accountName: string
  symbols: string[]
  filledPrompt: string
  exchange?: string  // Which exchange this preview is for
}

export interface PromptPreviewResponse {
  previews: PromptPreviewItem[]
}

export async function previewPrompt(
  payload: PromptPreviewRequest,
): Promise<PromptPreviewResponse> {
  const response = await apiRequest('/prompts/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json()
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
export async function getAccounts(options?: { include_hidden?: boolean }): Promise<TradingAccount[]> {
  const params = new URLSearchParams()
  if (options?.include_hidden) {
    params.set('include_hidden', 'true')
  }
  const queryString = params.toString()
  const url = queryString ? `/account/list?${queryString}` : '/account/list'
  const response = await apiRequest(url)
  return response.json()
}

export interface DashboardVisibilityUpdate {
  account_id: number
  show_on_dashboard: boolean
}

export async function updateDashboardVisibility(
  updates: DashboardVisibilityUpdate[]
): Promise<{ success: boolean; updated_count: number; updates: DashboardVisibilityUpdate[] }> {
  const response = await apiRequest('/account/dashboard-visibility', {
    method: 'PATCH',
    body: JSON.stringify(updates)
  })
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

export interface ArenaRelatedOrder {
  type: 'sl' | 'tp'
  price: number
  quantity: number
  notional: number
  commission: number
  trade_time?: string | null
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
  wallet_address?: string | null
  signal_trigger_id?: number | null
  prompt_template_id?: number | null
  prompt_template_name?: string | null
  decision_source_type?: 'prompt_template' | 'program' | null
  related_orders?: ArenaRelatedOrder[]
  // Exchange identifier (NULL treated as "hyperliquid" for backward compatibility)
  exchange?: string
}

export interface ArenaTradesResponse {
  generated_at: string
  accounts: ArenaAccountMeta[]
  trades: ArenaTrade[]
}

export async function getArenaTrades(params?: { limit?: number; account_id?: number; trading_mode?: string; wallet_address?: string, symbol?: string, exchange?: string }): Promise<ArenaTradesResponse> {
  const search = new URLSearchParams()
  if (params?.limit) search.append('limit', params.limit.toString())
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  if (params?.trading_mode) search.append('trading_mode', params.trading_mode)
  if (params?.wallet_address) search.append('wallet_address', params.wallet_address)
  if (params?.symbol) search.append('symbol', params.symbol)
  if (params?.exchange) search.append('exchange', params.exchange)
  const query = search.toString()
  const response = await apiRequest(`/arena/trades${query ? `?${query}` : ''}`)
  return response.json()
}

export interface UpdatePnlEnvironmentResult {
  fills_count: number
  unique_orders: number
  trades_updated: number
  trades_created: number
  decisions_updated: number
  program_logs_updated: number
  skipped: number
  historical_fixed?: number
}

export interface UpdatePnlResponse {
  success: boolean
  message?: string
  hyperliquid: Record<string, UpdatePnlEnvironmentResult>
  binance: Record<string, UpdatePnlEnvironmentResult>
  errors: string[]
}

export async function updateArenaPnl(): Promise<UpdatePnlResponse> {
  const response = await apiRequest('/arena/update-pnl', { method: 'POST' })
  return response.json()
}

export interface PnlSyncStatus {
  needs_sync: boolean
  unsync_count: number
}

export async function checkPnlSyncStatus(tradingMode?: string): Promise<PnlSyncStatus> {
  const params = new URLSearchParams()
  if (tradingMode) params.append('trading_mode', tradingMode)
  const query = params.toString()
  const response = await apiRequest(`/arena/check-pnl-status${query ? `?${query}` : ''}`)
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
  wallet_address?: string | null
  signal_trigger_id?: number | null
  prompt_template_id?: number | null
  prompt_template_name?: string | null
  // Exchange identifier (NULL treated as "hyperliquid" for backward compatibility)
  exchange?: string
}

export interface ArenaModelChatResponse {
  generated_at: string
  entries: ArenaModelChatEntry[]
}

export async function getArenaModelChat(params?: { limit?: number; account_id?: number; trading_mode?: string; wallet_address?: string; before_time?: string; after_time?: string; operation?: string; symbol?: string; exchange?: string }): Promise<ArenaModelChatResponse> {
  const search = new URLSearchParams()
  if (params?.limit) search.append('limit', params.limit.toString())
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  if (params?.trading_mode) search.append('trading_mode', params.trading_mode)
  if (params?.wallet_address) search.append('wallet_address', params.wallet_address)
  if (params?.before_time) search.append('before_time', params.before_time)
  if (params?.after_time) search.append('after_time', params.after_time)
  if (params?.operation) search.append('operation', params.operation)
  if (params?.symbol) search.append('symbol', params.symbol)
  if (params?.exchange) search.append('exchange', params.exchange)
  const query = search.toString()
  const response = await apiRequest(`/arena/model-chat${query ? `?${query}` : ''}`)
  return response.json()
}

export interface ModelChatSnapshots {
  id: number
  prompt_snapshot?: string | null
  reasoning_snapshot?: string | null
  decision_snapshot?: string | null
  error?: string
}

export async function getModelChatSnapshots(decisionId: number): Promise<ModelChatSnapshots> {
  const response = await apiRequest(`/arena/model-chat/${decisionId}/snapshots`)
  return response.json()
}

// Program Execution Log types and API
export interface ProgramExecutionLog {
  id: number
  binding_id: number
  account_id: number
  account_name: string
  program_id: number
  program_name: string
  trigger_type: string  // "signal" or "scheduled"
  trigger_symbol: string | null
  signal_pool_id: number | null
  signal_pool_name: string | null
  wallet_address: string | null
  success: boolean
  decision_action: string | null
  decision_symbol: string | null
  decision_size_usd: number | null
  decision_leverage: number | null
  decision_reason: string | null
  error_message: string | null
  execution_time_ms: number | null
  // Execution snapshots - expanded structure for analysis
  market_context: {
    input_data?: {
      environment?: string
      trigger_symbol?: string
      trigger_type?: string
      signal_pool_id?: number
      signal_pool_name?: string
      available_balance?: number
      total_equity?: number
      margin_usage_percent?: number
      positions?: Record<string, { side: string; size: number; entry_price: number; unrealized_pnl?: number; leverage?: number }>
      positions_count?: number
      open_orders_count?: number
      prices?: Record<string, number>
    }
    data_queries?: Array<{ method: string; args: Record<string, unknown>; result: unknown }>
    execution_logs?: string[]
    // Legacy fields for backward compatibility
    prices?: Record<string, number>
    available_balance?: number
  } | null
  params_snapshot: Record<string, unknown> | null
  decision_json: Record<string, unknown> | null
  created_at: string
  // Exchange identifier (NULL treated as "hyperliquid" for backward compatibility)
  exchange?: string
}

export async function getProgramExecutions(params?: {
  account_id?: number
  program_id?: number
  environment?: 'testnet' | 'mainnet'
  limit?: number
  before?: string
  after?: string
  action?: string
  exchange?: string
}): Promise<ProgramExecutionLog[]> {
  const search = new URLSearchParams()
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  if (params?.program_id) search.append('program_id', params.program_id.toString())
  if (params?.environment) search.append('environment', params.environment)
  if (params?.limit) search.append('limit', params.limit.toString())
  if (params?.before) search.append('before', params.before)
  if (params?.after) search.append('after', params.after)
  if (params?.action) search.append('action', params.action)
  if (params?.exchange) search.append('exchange', params.exchange)
  const query = search.toString()
  const response = await apiRequest(`/programs/executions/${query ? `?${query}` : ''}`)
  return response.json()
}

// Program Test Run types and API
export interface TestRunRequest {
  code: string
  symbol?: string
  period?: string
}

export interface ErrorLocation {
  file: string | null
  line: number | null
  column: number | null
  function: string | null
  code_context: string | null
}

export interface DecisionResult {
  action: string
  symbol: string | null
  size_usd: number | null
  leverage: number | null
  reason: string | null
}

export interface MarketDataSummary {
  symbol: string
  current_price: number | null
  price_change_1h: number | null
  klines_count: number
  indicators_loaded: string[]
}

export interface TestRunResponse {
  success: boolean
  // Success fields
  decision: DecisionResult | null
  execution_time_ms: number
  market_data: MarketDataSummary | null
  // Error fields
  error_type: string | null
  error_message: string | null
  error_traceback: string | null
  error_location: ErrorLocation | null
  suggestions: string[]
  available_apis: Record<string, unknown> | null
}

export async function testRunProgram(request: TestRunRequest): Promise<TestRunResponse> {
  const response = await apiRequest('/programs/test-run', {
    method: 'POST',
    body: JSON.stringify(request),
  })
  return response.json()
}

// Preview Run types and API (for testing with real account data)
export interface PreviewRunResponse {
  success: boolean
  error: string | null
  input_data: {
    trigger_symbol: string
    trigger_type: string
    environment: string
    available_balance: number
    total_equity: number
    used_margin: number
    margin_usage_percent: number
    positions: Record<string, {
      side: string
      size: number
      entry_price: number
      unrealized_pnl: number
    }>
    open_orders_count: number
    recent_trades_count: number
    current_price: number | null
  } | null
  data_queries: Array<{
    method: string
    args: Record<string, unknown>
    result: unknown
  }>
  execution_logs: string[]
  decision: Record<string, unknown> | null
  execution_time_ms: number
}

export async function previewRunBinding(bindingId: number): Promise<PreviewRunResponse> {
  const response = await apiRequest(`/programs/bindings/${bindingId}/preview-run`, {
    method: 'POST',
  })
  return response.json()
}

export interface ProgramDevGuideResponse {
  content: string
}

export async function getProgramDevGuide(lang: string = 'en'): Promise<ProgramDevGuideResponse> {
  const response = await apiRequest(`/programs/dev-guide?lang=${lang}`)
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
  leverage?: number | null
  margin_used?: number | null
  return_on_equity?: number | null
  percentage?: number | null
  margin_mode?: string | null
  liquidation_px?: number | null
  max_leverage?: number | null
  leverage_type?: string | null
}

export interface ArenaPositionsAccount {
  account_id: number
  account_name: string
  model?: string | null
  environment?: string | null
  exchange?: string
  wallet_address?: string | null
  total_unrealized_pnl: number
  available_cash: number
  used_margin?: number | null
  positions: ArenaPositionItem[]
  total_assets: number
  initial_capital: number
  total_return?: number | null
  margin_usage_percent?: number | null
  margin_mode?: string | null
}

export interface ArenaPositionsResponse {
  generated_at: string
  accounts: ArenaPositionsAccount[]
}

export async function getArenaPositions(params?: { account_id?: number; trading_mode?: string }): Promise<ArenaPositionsResponse> {
  const search = new URLSearchParams()
  if (params?.account_id) search.append('account_id', params.account_id.toString())
  if (params?.trading_mode) search.append('trading_mode', params.trading_mode)
  const query = search.toString()
  const response = await apiRequest(`/arena/positions${query ? `?${query}` : ''}`)
  const data = await response.json()

  const accounts = Array.isArray(data.accounts)
    ? data.accounts.map((account: any) => ({
        account_id: Number(account.account_id),
        account_name: account.account_name ?? '',
        model: account.model ?? null,
        environment: account.environment ?? null,
        exchange: account.exchange ?? 'hyperliquid',
        wallet_address: account.wallet_address ?? null,
        total_unrealized_pnl: Number(account.total_unrealized_pnl ?? 0),
        available_cash: Number(account.available_cash ?? 0),
        positions_value: Number(account.positions_value ?? account.used_margin ?? 0),
        used_margin: account.used_margin !== undefined ? Number(account.used_margin) : null,
        total_assets: Number(account.total_assets ?? 0),
        initial_capital: Number(account.initial_capital ?? 0),
        total_return:
          account.total_return !== undefined && account.total_return !== null
            ? Number(account.total_return)
            : null,
        margin_usage_percent:
          account.margin_usage_percent !== undefined && account.margin_usage_percent !== null
            ? Number(account.margin_usage_percent)
            : null,
        margin_mode: account.margin_mode ?? null,
        positions: Array.isArray(account.positions)
          ? account.positions.map((pos: any, idx: number) => ({
              id: pos.id ?? idx,
              symbol: pos.symbol ?? '',
              name: pos.name ?? '',
              market: pos.market ?? '',
              side: pos.side ?? '',
              quantity: Number(pos.quantity ?? 0),
              avg_cost: Number(pos.avg_cost ?? 0),
              current_price: Number(pos.current_price ?? 0),
              notional: Number(pos.notional ?? 0),
              current_value: Number(pos.current_value ?? 0),
              unrealized_pnl: Number(pos.unrealized_pnl ?? 0),
              leverage:
                pos.leverage !== undefined && pos.leverage !== null
                  ? Number(pos.leverage)
                  : null,
              margin_used:
                pos.margin_used !== undefined && pos.margin_used !== null
                  ? Number(pos.margin_used)
                  : null,
              return_on_equity:
                pos.return_on_equity !== undefined && pos.return_on_equity !== null
                  ? Number(pos.return_on_equity)
                  : null,
              percentage:
                pos.percentage !== undefined && pos.percentage !== null
                  ? Number(pos.percentage)
                  : null,
              margin_mode: pos.margin_mode ?? null,
              liquidation_px:
                pos.liquidation_px !== undefined && pos.liquidation_px !== null
                  ? Number(pos.liquidation_px)
                  : null,
              max_leverage:
                pos.max_leverage !== undefined && pos.max_leverage !== null
                  ? Number(pos.max_leverage)
                  : null,
              leverage_type: pos.leverage_type ?? null,
            }))
          : [],
      }))
    : []

  return {
    generated_at: data.generated_at ?? new Date().toISOString(),
    accounts,
  }
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

// Hyperliquid symbol configuration
export interface HyperliquidSymbolMeta {
  symbol: string
  name?: string
  type?: string
}

export interface HyperliquidAvailableSymbolsResponse {
  symbols: HyperliquidSymbolMeta[]
  updated_at?: string
  max_symbols: number
}

export interface HyperliquidWatchlistResponse {
  symbols: string[]
  max_symbols: number
}

export async function getHyperliquidAvailableSymbols(): Promise<HyperliquidAvailableSymbolsResponse> {
  const response = await apiRequest('/hyperliquid/symbols/available')
  return response.json()
}

export async function getHyperliquidWatchlist(): Promise<HyperliquidWatchlistResponse> {
  const response = await apiRequest('/hyperliquid/symbols/watchlist')
  return response.json()
}

export async function updateHyperliquidWatchlist(symbols: string[]): Promise<HyperliquidWatchlistResponse> {
  const response = await apiRequest('/hyperliquid/symbols/watchlist', {
    method: 'PUT',
    body: JSON.stringify({ symbols }),
  })
  return response.json()
}

// Binance Symbol APIs
export interface BinanceSymbolMeta {
  symbol: string
  name?: string
  type?: string
}

export interface BinanceAvailableSymbolsResponse {
  symbols: BinanceSymbolMeta[]
  count: number
  max_symbols: number
}

export interface BinanceWatchlistResponse {
  symbols: string[]
  max_symbols: number
}

export async function getBinanceAvailableSymbols(): Promise<BinanceAvailableSymbolsResponse> {
  const response = await apiRequest('/binance/symbols/available')
  return response.json()
}

export async function getBinanceWatchlist(): Promise<BinanceWatchlistResponse> {
  const response = await apiRequest('/binance/symbols/watchlist')
  return response.json()
}

export async function updateBinanceWatchlist(symbols: string[]): Promise<BinanceWatchlistResponse> {
  const response = await apiRequest('/binance/symbols/watchlist', {
    method: 'PUT',
    body: JSON.stringify({ symbols }),
  })
  return response.json()
}

export interface NewsSourceConfig {
  type: string
  adapter: string
  url: string
  enabled: boolean
  interval_seconds: number
  config?: Record<string, any>
}

export interface NewsSourcesResponse {
  sources: NewsSourceConfig[]
}

export interface NewsSourcesUpdateResponse {
  success: boolean
  message: string
  sources: NewsSourceConfig[]
}

export interface NewsSourcePreviewArticle {
  title: string
  summary: string
  published_at?: string | null
  source_domain?: string | null
  source_url: string
  validation_issues?: string[]
}

export interface NewsSourceValidationIssue {
  source_url: string
  issues: string[]
}

export interface NewsSourceValidationResult {
  schema_match: boolean
  valid_articles: number
  invalid_articles: number
  issues: NewsSourceValidationIssue[]
}

export interface TestNewsSourceResponse {
  success: boolean
  error?: string
  total_fetched?: number
  articles: NewsSourcePreviewArticle[]
  validation?: NewsSourceValidationResult
}

export interface NewsStatsResponse {
  total_articles: number
  classified: number
  with_sentiment: number
  last_24h: {
    by_domain: Record<string, number>
    by_sentiment: Record<string, number>
    total: number
  }
  latest_article_at?: string | null
}

export async function getNewsSources(): Promise<NewsSourcesResponse> {
  const response = await apiRequest('/news/sources')
  return response.json()
}

export async function updateNewsSources(sources: NewsSourceConfig[]): Promise<NewsSourcesUpdateResponse> {
  const response = await apiRequest('/news/sources', {
    method: 'PUT',
    body: JSON.stringify({ sources }),
  })
  return response.json()
}

export async function testNewsSource(
  payload: Pick<NewsSourceConfig, 'url' | 'adapter'> & { config?: Record<string, any> }
): Promise<TestNewsSourceResponse> {
  const response = await apiRequest('/news/sources/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json()
}

export async function getNewsStats(): Promise<NewsStatsResponse> {
  const response = await apiRequest('/news/stats')
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

// Membership interfaces
export interface MembershipInfo {
  status: string
  planKey: string
  planId?: string
  subscriptionId?: string
  environment: string
  currentPeriodStart?: string
  currentPeriodEnd?: string
  nextBillingTime?: string
  lastPaymentTime?: string
  updatedAt?: string
}

export interface MembershipEvent {
  id: number
  eventType: string
  status: string
  createdAt: string
  environment: string
}

export interface MembershipResponse {
  membership: MembershipInfo | null
  events?: MembershipEvent[]
}

// Get membership information from external membership service
// IMPORTANT: This function supports both same-domain and cross-domain access
// - Same-domain: Uses cookies automatically
// - Cross-domain (localhost/custom domains): Uses Authorization header with arena_token
// This ensures paid users can access membership features regardless of deployment domain
export async function getMembershipInfo(): Promise<MembershipResponse> {
  try {
    // Get arena_token for cross-domain authentication
    // This is the same Casdoor access token used for login
    const token = Cookies.get('arena_token')

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Add Authorization header if token exists (critical for localhost/custom domain deployments)
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch('https://www.akooi.com/api/membership/me', {
      method: 'GET',
      credentials: 'include',  // Still include credentials for same-domain cookie support
      headers,
    })

    if (!response.ok) {
      if (response.status === 401) {
        // User not authenticated or no membership
        // This can happen if:
        // 1. User is not logged in to www.akooi.com
        // 2. Cross-site cookies are blocked (localhost access with old cookies)
        // 3. Token has expired
        console.warn('[Membership] 401 Unauthorized - Please re-login at https://www.akooi.com to refresh your session')
        return { membership: null }
      }
      throw new Error(`Failed to fetch membership info: ${response.status}`)
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error('Error fetching membership info:', error)
    // Return null membership on error to gracefully degrade
    return { membership: null }
  }
}

// Hyperliquid Builder Fee Authorization APIs
export interface BuilderAuthorizationStatus {
  authorized: boolean
  max_fee: number
  required_fee: number
  builder_address: string
}

export interface UnauthorizedAccount {
  account_id: number
  account_name: string
  wallet_address: string
  max_fee: number
  required_fee: number
  error_message?: string
}

export interface CheckMainnetAccountsResponse {
  unauthorized_accounts: UnauthorizedAccount[]
}

export interface ApproveBuilderResponse {
  success: boolean
  message: string
  builder_address: string
  approved_fee: string
  result?: unknown
}

export interface DisableTradingResponse {
  success: boolean
  message: string
  account_id: number
  account_name: string
}

export async function checkBuilderAuthorization(walletAddress: string): Promise<BuilderAuthorizationStatus> {
  const response = await apiRequest(`/account/hyperliquid/check-builder-authorization?wallet_address=${walletAddress}`)
  return response.json()
}

export async function checkMainnetAccounts(): Promise<CheckMainnetAccountsResponse> {
  const response = await apiRequest('/account/hyperliquid/check-mainnet-accounts')
  return response.json()
}

export async function approveBuilder(accountId: number): Promise<ApproveBuilderResponse> {
  const response = await apiRequest(`/account/hyperliquid/approve-builder?account_id=${accountId}`, {
    method: 'POST'
  })
  return response.json()
}

export async function disableTrading(accountId: number): Promise<DisableTradingResponse> {
  const response = await apiRequest(`/account/${accountId}/disable-trading`, {
    method: 'POST'
  })
  return response.json()
}

// Trader Data Export/Import API
export interface TraderExportData {
  account_id: number
  account_name: string
  exported_at: string
  decision_logs: Array<{
    symbol: string
    decision_time: string
    operation: string
    reason?: string
    prev_portion?: number
    target_portion?: number
    total_balance?: number
    executed?: string
    prompt_snapshot?: string
    reasoning_snapshot?: string
    decision_snapshot?: string
    hyperliquid_environment?: string
    wallet_address?: string
    hyperliquid_order_id?: string
    tp_order_id?: string
    sl_order_id?: string
    realized_pnl?: number
    pnl_updated_at?: string
  }>
  trades: Array<{
    environment: string
    wallet_address: string
    symbol: string
    side: string
    quantity: number
    price: number
    leverage: number
    order_id: string
    trade_value: number
    fee: number
    trade_time: string
  }>
}

export interface ImportPreviewResponse {
  will_import: {
    decision_logs: number
    trades: number
  }
  will_skip: {
    decision_logs: number
    trades: number
  }
  details: {
    new_decision_times: string[]
    duplicate_decision_times: string[]
    new_trade_ids: string[]
    duplicate_trade_ids: string[]
  }
}

export interface ImportExecuteResponse {
  success: boolean
  imported: {
    decision_logs: number
    trades: number
  }
  skipped: {
    decision_logs: number
    trades: number
  }
  errors: string[]
}

export async function exportTraderData(accountId: number): Promise<TraderExportData> {
  const response = await apiRequest(`/trader/${accountId}/export`)
  return response.json()
}

export async function previewTraderImport(
  accountId: number,
  data: TraderExportData
): Promise<ImportPreviewResponse> {
  const response = await apiRequest(`/trader/${accountId}/import/preview`, {
    method: 'POST',
    body: JSON.stringify({ data })
  })
  return response.json()
}

export async function executeTraderImport(
  accountId: number,
  data: TraderExportData,
  confirmed: boolean = true
): Promise<ImportExecuteResponse> {
  const response = await apiRequest(`/trader/${accountId}/import/execute`, {
    method: 'POST',
    body: JSON.stringify({ data, confirmed })
  })
  return response.json()
}

// ============================================================================
// Prompt Backtest API
// ============================================================================

export interface BacktestItemInput {
  decision_log_id: number
  modified_prompt: string
}

export interface ReplaceRule {
  find: string
  replace: string
}

export interface CreateBacktestTaskRequest {
  account_id: number
  name?: string
  items: BacktestItemInput[]
  replace_rules?: ReplaceRule[]
}

export interface BacktestTask {
  id: number
  account_id: number
  name: string | null
  status: string
  total_count: number
  completed_count: number
  failed_count: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface BacktestResultItem {
  id: number
  original_decision_time: string | null
  original_operation: string | null
  original_symbol: string | null
  original_target_portion: number | null
  original_realized_pnl: number | null
  new_operation: string | null
  new_symbol: string | null
  new_target_portion: number | null
  decision_changed: boolean | null
  change_type: string | null
  status: string
}

export interface BacktestResultSummary {
  total: number
  completed: number
  failed: number
  changed: number
  unchanged: number
  avoided_loss_count: number
  avoided_loss_amount: number
  missed_profit_count: number
  missed_profit_amount: number
}

export interface BacktestItemDetail {
  id: number
  original_operation: string | null
  original_symbol: string | null
  original_reasoning: string | null
  original_decision_json: string | null
  original_prompt_template_name: string | null
  modified_prompt: string | null
  new_operation: string | null
  new_symbol: string | null
  new_reasoning: string | null
  new_decision_json: string | null
  decision_changed: boolean | null
  change_type: string | null
  error_message: string | null
}

export async function createBacktestTask(request: CreateBacktestTaskRequest) {
  const response = await apiRequest('/prompt-backtest/tasks', {
    method: 'POST',
    body: JSON.stringify(request)
  })
  return response.json()
}

export async function listBacktestTasks(accountId?: number, limit: number = 20) {
  const params = new URLSearchParams()
  if (accountId) params.append('account_id', String(accountId))
  params.append('limit', String(limit))
  const response = await apiRequest(`/prompt-backtest/tasks?${params}`)
  return response.json() as Promise<{ tasks: BacktestTask[] }>
}

export async function getBacktestTaskStatus(taskId: number) {
  const response = await apiRequest(`/prompt-backtest/tasks/${taskId}`)
  return response.json() as Promise<BacktestTask>
}

export async function getBacktestTaskResults(taskId: number) {
  const response = await apiRequest(`/prompt-backtest/tasks/${taskId}/results`)
  return response.json() as Promise<{
    task: BacktestTask
    items: BacktestResultItem[]
    summary: BacktestResultSummary
  }>
}

export async function getBacktestItemDetail(itemId: number) {
  const response = await apiRequest(`/prompt-backtest/items/${itemId}`)
  return response.json() as Promise<BacktestItemDetail>
}

export async function deleteBacktestTask(taskId: number) {
  const response = await apiRequest(`/prompt-backtest/tasks/${taskId}`, {
    method: 'DELETE'
  })
  return response.json()
}

export async function retryBacktestTask(taskId: number) {
  const response = await apiRequest(`/prompt-backtest/tasks/${taskId}/retry`, {
    method: 'POST'
  })
  return response.json() as Promise<{
    success: boolean
    message: string
    retry_count: number
  }>
}

export interface BacktestTaskItemForImport {
  id: number
  modified_prompt: string
  operation: string | null
  symbol: string | null
  reason: string | null
  decision_time: string | null
  realized_pnl: number | null
}

export async function getBacktestTaskItems(taskId: number) {
  const response = await apiRequest(`/prompt-backtest/tasks/${taskId}/items`)
  return response.json() as Promise<{
    task_id: number
    task_name: string
    items: BacktestTaskItemForImport[]
  }>
}

export interface MarketFlowSummaryItem {
  symbol: string
  exchange: string
  window: string
  start_time: number
  end_time: number
  latest_trade_timestamp?: number | null
  total_buy_notional: number
  total_sell_notional: number
  net_inflow: number
  buy_ratio: number
  total_large_buy_notional: number
  total_large_sell_notional: number
  large_order_net: number
  retail_net: number
  large_buy_count: number
  large_sell_count: number
  open_interest_change_pct?: number | null
  funding_rate_pct?: number | null
}

export interface MarketFlowSummaryResponse {
  exchange: string
  window: string
  items: MarketFlowSummaryItem[]
}

export interface NewsArticle {
  id: number
  source_domain: string
  source_url: string
  title: string
  summary?: string | null
  published_at?: string | null
  symbols: string[]
  sentiment?: string | null
  ai_summary?: string | null
  relevance_score?: number | null
  image_url?: string | null
}

export interface HyperAiInsightRequest {
  context: Record<string, unknown>
  selected_event?: Record<string, unknown> | null
  lang?: string
}

export async function startHyperAiInsightAnalysis(payload: HyperAiInsightRequest) {
  const response = await apiRequest('/hyper-ai/insight', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.json() as Promise<{ task_id: string }>
}

export interface NewsArticleListResponse {
  items: NewsArticle[]
  total: number
}

export interface LargeOrderZoneItem {
  time: number
  large_buy_notional: number
  large_sell_notional: number
  large_order_net: number
  large_buy_count: number
  large_sell_count: number
}

export interface LargeOrderZoneResponse {
  symbol: string
  exchange: string
  timeframe: string
  items: LargeOrderZoneItem[]
}

export async function getMarketFlowSummary(params: {
  symbols: string[]
  exchange: 'hyperliquid' | 'binance'
  window?: string
}) {
  const searchParams = new URLSearchParams()
  searchParams.set('symbols', params.symbols.join(','))
  searchParams.set('exchange', params.exchange)
  searchParams.set('window', params.window || '1h')
  const response = await apiRequest(`/market-flow/summary?${searchParams.toString()}`)
  return response.json() as Promise<MarketFlowSummaryResponse>
}

export async function getNewsArticles(params: {
  symbols?: string[]
  hours?: number
  limit?: number
}) {
  const searchParams = new URLSearchParams()
  if (params.symbols?.length) {
    searchParams.set('symbols', params.symbols.join(','))
  }
  if (params.hours) {
    searchParams.set('hours', String(params.hours))
  }
  if (params.limit) {
    searchParams.set('limit', String(params.limit))
  }
  const response = await apiRequest(`/news/articles?${searchParams.toString()}`)
  return response.json() as Promise<NewsArticleListResponse>
}

export async function getLargeOrderZones(params: {
  symbol: string
  exchange: 'hyperliquid' | 'binance'
  timeframe: string
  startTime?: number
  endTime?: number
}) {
  const searchParams = new URLSearchParams()
  searchParams.set('symbol', params.symbol)
  searchParams.set('exchange', params.exchange)
  searchParams.set('timeframe', params.timeframe)
  if (params.startTime) searchParams.set('start_time', String(params.startTime))
  if (params.endTime) searchParams.set('end_time', String(params.endTime))
  const response = await apiRequest(`/market-flow/large-order-zones?${searchParams.toString()}`)
  return response.json() as Promise<LargeOrderZoneResponse>
}
