/**
 * Global Trading Mode Switch
 *
 * Allows switching between Testnet and Mainnet for all AI Traders
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import {
  getGlobalTradingMode,
  setGlobalTradingMode,
  type TradingModeInfo,
} from '@/lib/hyperliquidApi'

export default function TradingModeSwitch() {
  const [modeInfo, setModeInfo] = useState<TradingModeInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [switching, setSwitching] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [targetMode, setTargetMode] = useState<'testnet' | 'mainnet'>('testnet')

  useEffect(() => {
    loadModeInfo()
  }, [])

  const loadModeInfo = async () => {
    try {
      setLoading(true)
      const info = await getGlobalTradingMode()
      setModeInfo(info)
    } catch (error) {
      console.error('Failed to load trading mode:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSwitchClick = (newMode: 'testnet' | 'mainnet') => {
    setTargetMode(newMode)
    setShowConfirm(true)
  }

  const handleConfirmSwitch = async () => {
    try {
      setSwitching(true)
      const result = await setGlobalTradingMode(targetMode)

      if (result.success && result.changed) {
        toast.success(`✅ Switched to ${targetMode.toUpperCase()}`)
        await loadModeInfo()
      } else if (result.success && !result.changed) {
        toast('Already on ' + targetMode)
      } else {
        toast.error('Failed to switch trading mode')
      }

      setShowConfirm(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to switch mode'
      toast.error(message)
    } finally {
      setSwitching(false)
    }
  }

  if (loading && !modeInfo) {
    return (
      <div className="p-6 border rounded-lg">
        <div className="flex items-center justify-center">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  const isTestnet = modeInfo?.mode === 'testnet'

  return (
    <div className="p-6 border rounded-lg space-y-4">
      <div>
        <h3 className="text-lg font-medium mb-1">Global Trading Environment</h3>
        <p className="text-sm text-muted-foreground">
          Controls which network all AI Traders connect to
        </p>
      </div>

      {/* Current Mode Display */}
      <div className="p-4 rounded-lg bg-muted">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-muted-foreground mb-1">Current Mode</div>
            <div className="flex items-center gap-2">
              <div
                className={`text-2xl font-bold ${
                  isTestnet ? 'text-green-600' : 'text-orange-600'
                }`}
              >
                {isTestnet ? 'TESTNET' : 'MAINNET'}
              </div>
            </div>
            <div className="text-sm text-muted-foreground mt-1">
              {modeInfo?.description}
            </div>
          </div>
        </div>
      </div>

      {/* Mode Switch Buttons */}
      {!showConfirm ? (
        <div className="grid grid-cols-2 gap-3">
          <Button
            variant={isTestnet ? 'default' : 'outline'}
            onClick={() => handleSwitchClick('testnet')}
            disabled={isTestnet}
            className="h-20 flex-col"
          >
            <div className="text-lg font-semibold mb-1">TEST</div>
            <div>Testnet</div>
            <div className="text-xs opacity-70">Paper Trading</div>
          </Button>
          <Button
            variant={!isTestnet ? 'default' : 'outline'}
            onClick={() => handleSwitchClick('mainnet')}
            disabled={!isTestnet}
            className="h-20 flex-col"
          >
            <div className="text-lg font-semibold mb-1">MAIN</div>
            <div>Mainnet</div>
            <div className="text-xs opacity-70">Real Funds</div>
          </Button>
        </div>
      ) : (
        /* Confirmation Dialog */
        <div className="p-4 border-2 border-orange-500 rounded-lg space-y-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-5 w-5 text-orange-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-medium text-orange-700">
                {targetMode === 'mainnet'
                  ? 'Switch to MAINNET?'
                  : 'Switch back to TESTNET?'}
              </div>
              <div className="text-sm text-muted-foreground mt-1">
                {targetMode === 'mainnet' ? (
                  <>
                    <p className="font-medium text-orange-700 mb-2">
                      ⚠️ WARNING: This will use REAL FUNDS!
                    </p>
                    <p>All AI Traders will connect to Hyperliquid Mainnet and execute trades with real money. Make sure:</p>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                      <li>All strategies have been thoroughly tested on Testnet</li>
                      <li>Wallet addresses have sufficient balance</li>
                      <li>You understand the risks involved</li>
                    </ul>
                  </>
                ) : (
                  <>
                    <p>All AI Traders will switch to Testnet (paper trading). No real funds will be used.</p>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              variant={targetMode === 'mainnet' ? 'destructive' : 'default'}
              onClick={handleConfirmSwitch}
              disabled={switching}
              className="flex-1"
            >
              {switching ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Switching...
                </>
              ) : (
                `Yes, switch to ${targetMode.toUpperCase()}`
              )}
            </Button>
            <Button
              variant="outline"
              onClick={() => setShowConfirm(false)}
              disabled={switching}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="text-xs text-muted-foreground space-y-1">
        <p>
          • <strong>Testnet:</strong> Safe testing environment with fake funds. Perfect for strategy development.
        </p>
        <p>
          • <strong>Mainnet:</strong> Real trading with actual funds. Only switch when strategies are proven.
        </p>
      </div>
    </div>
  )
}
