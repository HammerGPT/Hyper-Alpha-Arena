/**
 * Global Trading Mode Context
 * Manages trading mode state (testnet/mainnet) across the application
 *
 * Architecture:
 * - Backend maintains the source of truth in SystemConfig table
 * - Frontend syncs with backend on mount and after every mode switch
 * - localStorage is used only for initial render to avoid flash
 */

'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { setGlobalTradingMode, getGlobalTradingMode } from '@/lib/hyperliquidApi';

export type TradingMode = 'testnet' | 'mainnet';

interface TradingModeContextType {
  tradingMode: TradingMode;
  setTradingMode: (mode: TradingMode) => void;
}

const TradingModeContext = createContext<TradingModeContextType | undefined>(undefined);

export function TradingModeProvider({ children }: { children: ReactNode }) {
  // Load from localStorage synchronously on initialization (avoid flash)
  const getInitialMode = (): TradingMode => {
    if (typeof window === 'undefined') return 'testnet';
    const saved = localStorage.getItem('trading_mode');
    return (saved === 'testnet' || saved === 'mainnet') ? saved : 'testnet';
  };

  const [tradingMode, setTradingModeState] = useState<TradingMode>(getInitialMode);

  // Sync with backend on mount to get the source of truth
  useEffect(() => {
    const syncWithBackend = async () => {
      try {
        console.log('[TradingModeContext] Syncing with backend on mount...');
        const response = await getGlobalTradingMode();
        const backendMode = response.mode as TradingMode;
        console.log('[TradingModeContext] Backend trading mode:', backendMode);

        // Update local state if backend differs from localStorage
        const localMode = localStorage.getItem('trading_mode');
        if (backendMode !== localMode) {
          console.log(`[TradingModeContext] Syncing: localStorage=${localMode}, backend=${backendMode}`);
          localStorage.setItem('trading_mode', backendMode);
          setTradingModeState(backendMode);
        }
      } catch (error) {
        console.error('[TradingModeContext] Failed to sync with backend on mount:', error);
      }
    };

    syncWithBackend();
  }, []);

  // Save to localStorage when changed and sync with backend before reload
  const setTradingMode = async (mode: TradingMode) => {
    console.log('[TradingModeContext] Switching to:', mode);
    try {
      // Sync with backend first
      console.log('[TradingModeContext] Calling setGlobalTradingMode API...');
      const result = await setGlobalTradingMode(mode);
      console.log('[TradingModeContext] API response:', result);

      // Save to localStorage
      localStorage.setItem('trading_mode', mode);
      console.log('[TradingModeContext] Saved to localStorage, reloading...');

      // Reload to apply changes
      window.location.reload();
    } catch (error) {
      console.error('[TradingModeContext] Failed to sync trading mode with backend:', error);
      // Still save locally and reload even if backend sync fails
      localStorage.setItem('trading_mode', mode);
      window.location.reload();
    }
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
