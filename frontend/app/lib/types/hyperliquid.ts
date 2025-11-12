/**
 * Hyperliquid type definitions for frontend
 */

export type HyperliquidEnvironment = 'testnet' | 'mainnet';

export interface HyperliquidConfig {
  enabled: boolean;
  environment: HyperliquidEnvironment;
  maxLeverage: number;
  defaultLeverage: number;
  hasTestnetKey: boolean;
  hasMainnetKey: boolean;
}

export interface HyperliquidBalance {
  totalEquity: number;
  availableBalance: number;
  usedMargin: number;
  marginUsagePercent: number;
  maintenanceMargin: number;
  withdrawalAvailable?: number;
  lastUpdated: string;
  walletAddress?: string;
}

export interface HyperliquidPosition {
  coin: string;
  szi: number; // signed size (positive = long, negative = short)
  entryPx: number; // entry price
  positionValue: number;
  unrealizedPnl: number;
  marginUsed: number;
  liquidationPx: number; // liquidation price
  leverage: number;
}

export interface HyperliquidPositionsResponse {
  positions: HyperliquidPosition[];
  count: number;
  environment?: HyperliquidEnvironment | string;
  source: 'cache' | 'live';
  cachedAt?: string;
}

export interface HyperliquidAccountState {
  marginSummary: {
    accountValue: number;
    totalMarginUsed: number;
    totalNtlPos: number; // total notional position value
    totalRawUsd: number; // total raw USD balance
  };
  crossMaintenanceMarginUsed: number;
  crossMarginSummary: {
    accountValue: number;
    totalMarginUsed: number;
    totalNtlPos: number;
    totalRawUsd: number;
  };
  positions: HyperliquidPosition[];
}

export interface SetupRequest {
  environment: HyperliquidEnvironment;
  privateKey: string;
  maxLeverage?: number;
  defaultLeverage?: number;
}

export interface SwitchEnvironmentRequest {
  targetEnvironment: HyperliquidEnvironment;
  confirm: boolean;
}

export interface ManualOrderRequest {
  symbol: string;
  is_buy: boolean;
  size: number;
  order_type: 'market' | 'limit';
  price?: number;
  reduce_only?: boolean;
  leverage?: number;
  environment?: HyperliquidEnvironment;
}

export interface OrderResult {
  status: 'filled' | 'resting';
  orderId: string;
  filledAmount: number;
  averagePrice: number;
}

export interface TestConnectionResponse {
  success: boolean;
  environment: HyperliquidEnvironment;
  address: string;
  balance?: number;
  message?: string;
}

export interface HyperliquidHealthResponse {
  status: string;
  service: string;
  encryptionConfigured: boolean;
  endpoints: {
    setup: string;
    balance: string;
    positions: string;
    test: string;
  };
}

export interface ApiError {
  detail: string;
}

export type PositionSide = 'LONG' | 'SHORT';

export interface PositionDisplay extends HyperliquidPosition {
  side: PositionSide;
  sizeAbs: number;
  pnlPercent: number;
  riskLevel: 'low' | 'medium' | 'high';
}

export interface MarginStatus {
  level: 'healthy' | 'warning' | 'danger';
  color: string;
  message: string;
}

export interface HyperliquidActionSummaryEntry {
  actionType: string;
  count: number;
  errors: number;
  lastOccurrence?: string | null;
}

export interface HyperliquidActionSummary {
  windowMinutes: number;
  accountId?: number;
  totalActions: number;
  generatedAt: string;
  latestActionAt?: string | null;
  byAction: HyperliquidActionSummaryEntry[];
}
