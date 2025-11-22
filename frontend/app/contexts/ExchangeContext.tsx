/**
 * Exchange selection context for managing current exchange state
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import {
  ExchangeId,
  ExchangeInfo,
  ExchangeContextType,
  DEFAULT_EXCHANGE,
  EXCHANGE_DISPLAY_NAMES,
  EXCHANGE_STATUS_COLORS
} from '@/lib/types/exchange';

const ExchangeContext = createContext<ExchangeContextType | undefined>(undefined);

interface ExchangeProviderProps {
  children: ReactNode;
}

// Storage key for persisting exchange selection
const STORAGE_KEY = 'hyper-alpha-arena-selected-exchange';

export function ExchangeProvider({ children }: ExchangeProviderProps) {
  const [currentExchange, setCurrentExchange] = useState<ExchangeId>(DEFAULT_EXCHANGE);
  const [isLoading, setIsLoading] = useState(false);

  // Initialize exchange selection from backend
  useEffect(() => {
    const loadExchangeConfig = async () => {
      try {
        const response = await fetch('/api/users/exchange-config');
        if (response.ok) {
          const data = await response.json();
          if (data.selected_exchange && ['hyperliquid', 'binance', 'aster'].includes(data.selected_exchange)) {
            setCurrentExchange(data.selected_exchange as ExchangeId);
          }
        } else {
          // Fallback to localStorage if backend fails
          const stored = localStorage.getItem(STORAGE_KEY);
          if (stored && ['hyperliquid', 'binance', 'aster'].includes(stored)) {
            setCurrentExchange(stored as ExchangeId);
          }
        }
      } catch (error) {
        console.warn('Failed to load exchange config from backend, using localStorage:', error);
        // Fallback to localStorage
        try {
          const stored = localStorage.getItem(STORAGE_KEY);
          if (stored && ['hyperliquid', 'binance', 'aster'].includes(stored)) {
            setCurrentExchange(stored as ExchangeId);
          }
        } catch (localError) {
          console.warn('Failed to load from localStorage:', localError);
        }
      }
    };

    loadExchangeConfig();
  }, []);

  // Exchange data with selection state
  const exchanges: ExchangeInfo[] = [
    {
      id: 'hyperliquid',
      name: 'Hyperliquid',
      displayName: 'Hyperliquid',
      selectable: true,
      selected: currentExchange === 'hyperliquid',
      apiSupported: true,
      comingSoon: false,
      logo: '/static/hyperliquid_logo.png',
      description: 'Decentralized perpetual futures exchange',
      features: ['No KYC Required', 'Low Fees', 'High Performance'],
      referralLink: 'https://app.hyperliquid.xyz/trade',
      buttonText: 'Open Futures',
      buttonVariant: 'default'
    },
    {
      id: 'binance',
      name: 'Binance',
      displayName: 'Binance',
      selectable: false,
      selected: currentExchange === 'binance',
      apiSupported: false,
      comingSoon: true,
      logo: '/static/binance_logo.png',
      description: 'World\'s largest cryptocurrency exchange',
      features: ['30% Fee Discount', 'High Liquidity', 'Advanced Tools'],
      referralLink: 'https://accounts.maxweb.red/register?ref=HYPERVIP',
      buttonText: 'Register First',
      buttonVariant: 'outline'
    },
    {
      id: 'aster',
      name: 'Aster DEX',
      displayName: 'Aster DEX',
      selectable: false,
      selected: currentExchange === 'aster',
      apiSupported: false,
      comingSoon: true,
      logo: '/static/aster_logo.png',
      description: 'Binance-compatible decentralized exchange',
      features: ['Lower Fees', 'Multi-chain Support', 'API Wallet Security'],
      referralLink: 'https://www.asterdex.com/zh-CN/referral/2b5924',
      buttonText: 'Register First',
      buttonVariant: 'outline'
    }
  ];

  const selectExchange = async (exchangeId: ExchangeId) => {
    if (exchangeId === currentExchange) return;

    // Only allow selection of supported exchanges
    const exchange = exchanges.find(ex => ex.id === exchangeId);
    if (!exchange?.selectable) {
      console.warn(`Exchange ${exchangeId} is not selectable yet`);
      return;
    }

    setIsLoading(true);

    try {
      // Save to backend first
      const response = await fetch('/api/users/exchange-config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ selected_exchange: exchangeId }),
      });

      if (!response.ok) {
        throw new Error(`Backend save failed: ${response.status}`);
      }

      // Update state
      setCurrentExchange(exchangeId);

      // Also persist to localStorage as backup
      localStorage.setItem(STORAGE_KEY, exchangeId);

      console.log(`Exchange switched to: ${EXCHANGE_DISPLAY_NAMES[exchangeId]}`);
    } catch (error) {
      console.error('Failed to switch exchange:', error);
      // Try localStorage fallback
      try {
        localStorage.setItem(STORAGE_KEY, exchangeId);
        setCurrentExchange(exchangeId);
        console.log(`Exchange switched to: ${EXCHANGE_DISPLAY_NAMES[exchangeId]} (localStorage fallback)`);
      } catch (localError) {
        console.error('Failed to save to localStorage:', localError);
        // Revert on complete failure
        setCurrentExchange(currentExchange);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const contextValue: ExchangeContextType = {
    currentExchange,
    exchanges,
    selectExchange,
    isLoading
  };

  return (
    <ExchangeContext.Provider value={contextValue}>
      {children}
    </ExchangeContext.Provider>
  );
}

export function useExchange(): ExchangeContextType {
  const context = useContext(ExchangeContext);
  if (context === undefined) {
    throw new Error('useExchange must be used within an ExchangeProvider');
  }
  return context;
}

// Helper hooks for common use cases
export function useCurrentExchange(): ExchangeId {
  const { currentExchange } = useExchange();
  return currentExchange;
}

export function useCurrentExchangeInfo(): ExchangeInfo {
  const { currentExchange, exchanges } = useExchange();
  return exchanges.find(ex => ex.id === currentExchange) || exchanges[0];
}