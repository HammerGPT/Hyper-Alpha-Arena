/**
 * Hyperliquid API service module
 */

import { apiRequest } from './api';
import type {
  HyperliquidConfig,
  HyperliquidBalance,
  HyperliquidAccountState,
  HyperliquidPositionsResponse,
  HyperliquidActionSummary,
  SetupRequest,
  SwitchEnvironmentRequest,
  ManualOrderRequest,
  OrderResult,
  TestConnectionResponse,
  HyperliquidHealthResponse,
} from './types/hyperliquid';

const HYPERLIQUID_API_BASE = '/hyperliquid';

/**
 * Configuration Management
 */
export async function setupHyperliquidAccount(
  accountId: number,
  config: SetupRequest
): Promise<{ success: boolean; message: string }> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/setup`,
    {
      method: 'POST',
      body: JSON.stringify(config),
    }
  );
  return response.json();
}

export async function getHyperliquidConfig(
  accountId: number
): Promise<HyperliquidConfig> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/config`
  );
  return response.json();
}

export async function switchEnvironment(
  accountId: number,
  request: SwitchEnvironmentRequest
): Promise<{ success: boolean; message: string }> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/switch-environment`,
    {
      method: 'POST',
      body: JSON.stringify(request),
    }
  );
  return response.json();
}

/**
 * Account State & Balance
 */
export async function getHyperliquidBalance(
  accountId: number,
  environment?: 'testnet' | 'mainnet'
): Promise<HyperliquidBalance> {
  const params = new URLSearchParams();
  if (environment) {
    params.append('environment', environment);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/balance${query}`
  );
  const data = await response.json();
  const lastUpdated =
    data.cached_at ??
    (data.timestamp ? new Date(data.timestamp).toISOString() : undefined);
  return {
    totalEquity: data.total_equity ?? 0,
    availableBalance: data.available_balance ?? 0,
    usedMargin: data.used_margin ?? 0,
    maintenanceMargin: data.maintenance_margin ?? 0,
    marginUsagePercent: data.margin_usage_percent ?? 0,
    withdrawalAvailable: data.withdrawal_available ?? 0,
    lastUpdated,
    walletAddress: data.wallet_address ?? undefined,
  };
}

export async function getHyperliquidAccountState(
  accountId: number
): Promise<HyperliquidAccountState> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/account-state`
  );
  return response.json();
}

/**
 * Positions Management
 */
export async function getHyperliquidPositions(
  accountId: number,
  environment?: 'testnet' | 'mainnet'
): Promise<HyperliquidPositionsResponse> {
  const params = new URLSearchParams();
  if (environment) {
    params.append('environment', environment);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/positions${query}`
  );
  const data = await response.json();
  const positions = Array.isArray(data.positions) ? data.positions : [];

  return {
    positions: positions.map((pos: any) => ({
      coin: pos.coin ?? pos.symbol ?? '',
      szi: Number(pos.szi ?? pos.contracts ?? 0),
      entryPx: Number(pos.entry_px ?? pos.entryPx ?? 0),
      positionValue: Number(pos.position_value ?? pos.positionValue ?? 0),
      unrealizedPnl: Number(pos.unrealized_pnl ?? pos.unrealizedPnl ?? 0),
      marginUsed: Number(pos.margin_used ?? pos.marginUsed ?? 0),
      liquidationPx: Number(pos.liquidation_px ?? pos.liquidationPx ?? 0),
      leverage: Number(pos.leverage ?? 1),
    })),
    count: data.count ?? positions.length,
    environment: data.environment,
    source: data.source ?? 'live',
    cachedAt: data.cached_at,
  };
}

/**
 * Market Data
 */
export async function getCurrentPrice(symbol: string): Promise<number> {
  const response = await apiRequest(`/market/price/${symbol}?market=CRYPTO`);
  const data = await response.json();
  return Number(data.price ?? 0);
}

/**
 * Order Management
 */
export async function placeManualOrder(
  accountId: number,
  order: ManualOrderRequest
): Promise<OrderResult> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/orders/manual`,
    {
      method: 'POST',
      body: JSON.stringify(order),
    }
  );
  return response.json();
}

/**
 * Testing & Health
 */
export async function testConnection(
  accountId: number
): Promise<TestConnectionResponse> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/test-connection`
  );
  return response.json();
}

export async function getHyperliquidHealth(): Promise<HyperliquidHealthResponse> {
  const response = await apiRequest(`${HYPERLIQUID_API_BASE}/health`);
  return response.json();
}

export async function getHyperliquidActionSummary(params?: {
  accountId?: number;
  windowMinutes?: number;
}): Promise<HyperliquidActionSummary> {
  const search = new URLSearchParams();
  if (params?.accountId) {
    search.append('account_id', params.accountId.toString());
  }
  if (params?.windowMinutes) {
    search.append('window_minutes', params.windowMinutes.toString());
  }
  const query = search.toString() ? `?${search.toString()}` : '';
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/actions/summary${query}`
  );
  const data = await response.json();
  return {
    windowMinutes: data.window_minutes ?? params?.windowMinutes ?? 1440,
    accountId: data.account_id ?? params?.accountId,
    totalActions: data.total_actions ?? 0,
    generatedAt: data.generated_at,
    latestActionAt: data.latest_action_at,
    byAction: Array.isArray(data.by_action)
      ? data.by_action.map((entry: any) => ({
          actionType: entry.action_type,
          count: entry.count ?? 0,
          errors: entry.errors ?? 0,
          lastOccurrence: entry.last_occurrence,
        }))
      : [],
  };
}

/**
 * Account Control
 */
export async function enableHyperliquid(
  accountId: number
): Promise<{ success: boolean; message: string }> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/enable`,
    {
      method: 'POST',
    }
  );
  return response.json();
}

export async function disableHyperliquid(
  accountId: number
): Promise<{ success: boolean; message: string }> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/disable`,
    {
      method: 'POST',
    }
  );
  return response.json();
}

/**
 * Utility Functions
 */

export function calculateMarginUsageColor(percent: number): string {
  if (percent < 50) return 'text-green-500';
  if (percent < 75) return 'text-yellow-500';
  return 'text-red-500';
}

export function formatPnl(pnl: number): {
  value: string;
  color: string;
  icon: string;
} {
  const isPositive = pnl >= 0;
  return {
    value: `${isPositive ? '+' : ''}${pnl.toFixed(2)}`,
    color: isPositive ? 'text-green-600' : 'text-red-600',
    icon: isPositive ? '↑' : '↓',
  };
}

export function getPositionSide(szi: number): 'LONG' | 'SHORT' {
  return szi > 0 ? 'LONG' : 'SHORT';
}

export function formatLeverage(leverage: number): string {
  return `${leverage}x`;
}

export function validatePrivateKey(key: string): boolean {
  // Must start with 0x and be 66 characters total (0x + 64 hex chars)
  return /^0x[0-9a-fA-F]{64}$/.test(key);
}

export function estimateLiquidationPrice(
  entryPrice: number,
  leverage: number,
  isLong: boolean
): number {
  // Simplified liquidation price estimation
  // Actual calculation is more complex and depends on margin mode
  const liquidationPercent = 1 / leverage;
  if (isLong) {
    return entryPrice * (1 - liquidationPercent);
  } else {
    return entryPrice * (1 + liquidationPercent);
  }
}

export function calculateRequiredMargin(
  size: number,
  price: number,
  leverage: number
): number {
  return (size * price) / leverage;
}

export function getRiskLevel(marginPercent: number): 'low' | 'medium' | 'high' {
  if (marginPercent < 50) return 'low';
  if (marginPercent < 75) return 'medium';
  return 'high';
}

/**
 * Rate Limit Management
 */
export async function getWalletRateLimit(
  accountId: number
): Promise<{
  success: boolean;
  accountId: number;
  rateLimit: {
    cumVlm: number;
    nRequestsUsed: number;
    nRequestsCap: number;
    nRequestsSurplus: number;
    remaining: number;
    usagePercent: number;
    isOverLimit: boolean;
    environment: string;
    walletAddress: string;
  };
}> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/rate-limit`
  );
  return response.json();
}

/**
 * Wallet Management (Multi-Wallet Architecture)
 */

export interface WalletConfig {
  id: number;
  walletAddress: string;
  maxLeverage: number;
  defaultLeverage: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WalletConfigRequest {
  privateKey: string;
  maxLeverage: number;
  defaultLeverage: number;
}

export interface WalletInfo {
  success: boolean;
  configured: boolean;
  accountId: number;
  accountName: string;
  wallet?: WalletConfig;
  globalTradingMode?: string;
  balance?: {
    totalEquity: number;
    availableBalance: number;
    marginUsagePercent: number;
  };
}

export async function getAccountWallet(accountId: number): Promise<WalletInfo> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/wallet`
  );
  return response.json();
}

export async function configureAccountWallet(
  accountId: number,
  config: WalletConfigRequest
): Promise<{ success: boolean; walletId: number; walletAddress: string; message: string }> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/wallet`,
    {
      method: 'POST',
      body: JSON.stringify(config),
    }
  );
  return response.json();
}

export async function deleteAccountWallet(
  accountId: number,
  environment: 'testnet' | 'mainnet'
): Promise<{ success: boolean; message: string; environment: string }> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/wallet?environment=${environment}`,
    {
      method: 'DELETE',
    }
  );
  return response.json();
}

export async function testWalletConnection(
  accountId: number
): Promise<{
  success: boolean;
  accountId: number;
  accountName: string;
  environment: string;
  walletAddress?: string;
  connection: string;
  accountState?: {
    totalEquity: number;
    availableBalance: number;
    marginUsage: number;
  };
  error?: string;
}> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/wallet/test`,
    {
      method: 'POST',
    }
  );
  return response.json();
}

/**
 * Global Trading Mode Management
 */

export interface TradingModeInfo {
  success: boolean;
  mode: 'testnet' | 'mainnet';
  description: string;
}

export async function getGlobalTradingMode(): Promise<TradingModeInfo> {
  const response = await apiRequest(`${HYPERLIQUID_API_BASE}/trading-mode`);
  return response.json();
}

export async function setGlobalTradingMode(
  mode: 'testnet' | 'mainnet'
): Promise<{
  success: boolean;
  mode: string;
  changed: boolean;
  oldMode?: string;
  message: string;
}> {
  const response = await apiRequest(`${HYPERLIQUID_API_BASE}/trading-mode`, {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
  return response.json();
}
