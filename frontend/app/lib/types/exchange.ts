/**
 * Exchange selection and management types
 */

export type ExchangeId = 'hyperliquid' | 'binance' | 'aster';

export interface ExchangeInfo {
  id: ExchangeId;
  name: string;
  displayName: string;
  selectable: boolean;
  selected: boolean;
  apiSupported: boolean;
  comingSoon: boolean;
  // Existing referral fields
  logo: string;
  description: string;
  features: string[];
  referralLink: string;
  buttonText: string;
  buttonVariant: 'default' | 'outline';
  proTip?: string;
}

export interface ExchangeSelection {
  current: ExchangeId;
  available: ExchangeId[];
}

export interface ExchangeContextType {
  currentExchange: ExchangeId;
  exchanges: ExchangeInfo[];
  selectExchange: (exchangeId: ExchangeId) => void;
  isLoading: boolean;
}

export const DEFAULT_EXCHANGE: ExchangeId = 'hyperliquid';

export const EXCHANGE_DISPLAY_NAMES: Record<ExchangeId, string> = {
  hyperliquid: 'Hyperliquid',
  binance: 'Binance',
  aster: 'Aster DEX'
};

export const EXCHANGE_STATUS_COLORS: Record<ExchangeId, string> = {
  hyperliquid: '🟢',
  binance: '🟡',
  aster: '🟡'
};