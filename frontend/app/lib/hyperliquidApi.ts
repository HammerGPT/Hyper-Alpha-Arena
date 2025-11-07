/**
 * Hyperliquid API service module
 */

import { apiRequest } from './api';
import type {
  HyperliquidConfig,
  HyperliquidBalance,
  HyperliquidPosition,
  HyperliquidAccountState,
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
  accountId: number
): Promise<HyperliquidBalance> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/balance`
  );
  const data = await response.json();
  return {
    totalEquity: data.total_equity ?? 0,
    availableBalance: data.available_balance ?? 0,
    usedMargin: data.used_margin ?? 0,
    maintenanceMargin: data.maintenance_margin ?? 0,
    marginUsagePercent: data.margin_usage_percent ?? 0,
    withdrawalAvailable: data.withdrawal_available ?? 0,
    lastUpdated: data.timestamp ? new Date(data.timestamp).toISOString() : undefined,
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
  accountId: number
): Promise<HyperliquidPosition[]> {
  const response = await apiRequest(
    `${HYPERLIQUID_API_BASE}/accounts/${accountId}/positions`
  );
  const data = await response.json();
  const positions = Array.isArray(data.positions) ? data.positions : [];

  return positions.map((pos: any) => ({
    coin: pos.coin ?? pos.symbol ?? '',
    szi: Number(pos.szi ?? pos.contracts ?? 0),
    entryPx: Number(pos.entry_px ?? pos.entryPx ?? 0),
    positionValue: Number(pos.position_value ?? pos.positionValue ?? 0),
    unrealizedPnl: Number(pos.unrealized_pnl ?? pos.unrealizedPnl ?? 0),
    marginUsed: Number(pos.margin_used ?? pos.marginUsed ?? 0),
    liquidationPx: Number(pos.liquidation_px ?? pos.liquidationPx ?? 0),
    leverage: Number(pos.leverage ?? 1),
  }));
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
