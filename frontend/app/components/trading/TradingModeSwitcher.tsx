/**
 * Trading Mode Switcher Component
 * Allows users to switch between Testnet and Mainnet
 */

import { useTradingMode, TradingMode } from '@/contexts/TradingModeContext';

export default function TradingModeSwitcher() {
  const { tradingMode, setTradingMode } = useTradingMode();

  const modes: { value: TradingMode; label: string; subtitle: string; color: string }[] = [
    {
      value: 'testnet',
      label: 'Testnet',
      subtitle: 'Test Money',
      color: 'bg-green-500 hover:bg-green-600',
    },
    {
      value: 'mainnet',
      label: 'Mainnet',
      subtitle: 'Real Money ⚠️',
      color: 'bg-red-500 hover:bg-red-600',
    },
  ];

  return (
    <div className="flex items-center space-x-2">
      <span className="text-xs font-medium text-gray-600">Mode:</span>
      <div className="inline-flex rounded-md border border-gray-300 bg-white p-0.5">
        {modes.map((mode) => (
          <button
            key={mode.value}
            onClick={() => setTradingMode(mode.value)}
            className={`
              px-3 py-1.5 rounded text-xs font-medium transition-all
              ${
                tradingMode === mode.value
                  ? `${mode.color} text-white shadow-sm`
                  : 'text-gray-700 hover:bg-gray-100'
              }
            `}
          >
            <div className="flex flex-col items-center">
              <span>{mode.label}</span>
              <span className="text-[10px] opacity-80 whitespace-nowrap">{mode.subtitle}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
