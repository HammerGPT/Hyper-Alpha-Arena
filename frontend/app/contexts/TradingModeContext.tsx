/**
 * Global Trading Mode Context
 * Manages trading mode state (testnet/mainnet) across the application
 */

'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type TradingMode = 'testnet' | 'mainnet';

interface TradingModeContextType {
  tradingMode: TradingMode;
  setTradingMode: (mode: TradingMode) => void;
}

const TradingModeContext = createContext<TradingModeContextType | undefined>(undefined);

export function TradingModeProvider({ children }: { children: ReactNode }) {
  // Load from localStorage synchronously on initialization
  const getInitialMode = (): TradingMode => {
    if (typeof window === 'undefined') return 'testnet';
    const saved = localStorage.getItem('trading_mode');
    return (saved === 'testnet' || saved === 'mainnet') ? saved : 'testnet';
  };

  const [tradingMode, setTradingModeState] = useState<TradingMode>(getInitialMode);

  // Save to localStorage when changed and reload page
  const setTradingMode = (mode: TradingMode) => {
    localStorage.setItem('trading_mode', mode);
    // Immediately reload without delay to avoid state conflicts
    window.location.reload();
  };

  return (
    <TradingModeContext.Provider value={{ tradingMode, setTradingMode }}>
      {children}
    </TradingModeContext.Provider>
  );
}

export function useTradingMode() {
  const context = useContext(TradingModeContext);
  if (context === undefined) {
    throw new Error('useTradingMode must be used within TradingModeProvider');
  }
  return context;
}
