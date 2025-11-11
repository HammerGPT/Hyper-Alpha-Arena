/**
 * Wallet Configuration Panel for AI Traders
 *
 * Allows configuring Hyperliquid wallet for each AI Trader independently
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Wallet, Eye, EyeOff, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import {
  getAccountWallet,
  configureAccountWallet,
  testWalletConnection,
  type WalletInfo,
} from '@/lib/hyperliquidApi'

interface WalletConfigPanelProps {
  accountId: number
  accountName: string
  onWalletConfigured?: () => void
}

export default function WalletConfigPanel({
  accountId,
  accountName,
  onWalletConfigured
}: WalletConfigPanelProps) {
  const [walletInfo, setWalletInfo] = useState<WalletInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [showPrivateKey, setShowPrivateKey] = useState(false)
  const [editing, setEditing] = useState(false)

  // Form state
  const [privateKey, setPrivateKey] = useState('')
  const [maxLeverage, setMaxLeverage] = useState(3)
  const [defaultLeverage, setDefaultLeverage] = useState(1)

  useEffect(() => {
    loadWalletInfo()
  }, [accountId])

  const loadWalletInfo = async () => {
    try {
      setLoading(true)
      const info = await getAccountWallet(accountId)
      setWalletInfo(info)

      if (info.wallet) {
        setMaxLeverage(info.wallet.maxLeverage)
        setDefaultLeverage(info.wallet.defaultLeverage)
      }
    } catch (error) {
      console.error('Failed to load wallet info:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveWallet = async () => {
    if (!privateKey.trim()) {
      toast.error('Please enter a private key')
      return
    }

    // Validate private key format
    if (!privateKey.startsWith('0x') || privateKey.length !== 66) {
      toast.error('Invalid private key format. Must be 0x followed by 64 hex characters')
      return
    }

    if (maxLeverage < 1 || maxLeverage > 50) {
      toast.error('Max leverage must be between 1 and 50')
      return
    }

    if (defaultLeverage < 1 || defaultLeverage > maxLeverage) {
      toast.error(`Default leverage must be between 1 and ${maxLeverage}`)
      return
    }

    try {
      setLoading(true)
      const result = await configureAccountWallet(accountId, {
        privateKey,
        maxLeverage,
        defaultLeverage,
      })

      if (result.success) {
        toast.success(`Wallet configured: ${result.walletAddress.substring(0, 10)}...`)
        setPrivateKey('')
        setEditing(false)
        await loadWalletInfo()
        onWalletConfigured?.()
      } else {
        toast.error('Failed to configure wallet')
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to configure wallet'
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  const handleTestConnection = async () => {
    try {
      setTesting(true)
      const result = await testWalletConnection(accountId)

      if (result.success && result.connection === 'successful') {
        toast.success(`✅ Connection successful! Balance: $${result.accountState?.totalEquity.toFixed(2)}`)
      } else {
        toast.error(`❌ Connection failed: ${result.error || 'Unknown error'}`)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Connection test failed'
      toast.error(message)
    } finally {
      setTesting(false)
    }
  }

  if (loading && !walletInfo) {
    return (
      <div className="p-4 border rounded-lg">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 border rounded-lg space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wallet className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-medium">Hyperliquid Wallet</h3>
        </div>
        {walletInfo?.configured && !editing && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(true)}
          >
            Update Wallet
          </Button>
        )}
      </div>

      {walletInfo?.globalTradingMode && (
        <div className="text-sm">
          <span className="text-muted-foreground">Global Mode:</span>{' '}
          <span className={walletInfo.globalTradingMode === 'testnet' ? 'text-green-600' : 'text-orange-600'}>
            {walletInfo.globalTradingMode === 'testnet' ? '🧪 Testnet' : '💰 Mainnet'}
          </span>
        </div>
      )}

      {walletInfo?.configured && !editing ? (
        // Display existing wallet
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-sm text-muted-foreground">Wallet Address</label>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 bg-muted rounded text-sm">
                {walletInfo.wallet?.walletAddress}
              </code>
              <CheckCircle className="h-5 w-5 text-green-600" />
            </div>
          </div>

          {walletInfo.balance && (
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div>
                <div className="text-muted-foreground">Balance</div>
                <div className="font-medium">${walletInfo.balance.totalEquity.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Available</div>
                <div className="font-medium">${walletInfo.balance.availableBalance.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Margin Usage</div>
                <div className="font-medium">{walletInfo.balance.marginUsagePercent.toFixed(1)}%</div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <div className="text-muted-foreground">Max Leverage</div>
              <div className="font-medium">{walletInfo.wallet?.maxLeverage}x</div>
            </div>
            <div>
              <div className="text-muted-foreground">Default Leverage</div>
              <div className="font-medium">{walletInfo.wallet?.defaultLeverage}x</div>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleTestConnection}
            disabled={testing}
            className="w-full"
          >
            {testing ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                Testing...
              </>
            ) : (
              'Test Connection'
            )}
          </Button>
        </div>
      ) : (
        // Configuration form
        <div className="space-y-3">
          {!walletInfo?.configured && (
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm">
              <p className="text-yellow-800">
                ⚠️ No wallet configured. This AI Trader cannot execute trades without a wallet.
              </p>
            </div>
          )}

          <div className="space-y-1">
            <label className="text-sm text-muted-foreground">Private Key</label>
            <div className="flex gap-2">
              <Input
                type={showPrivateKey ? 'text' : 'password'}
                value={privateKey}
                onChange={(e) => setPrivateKey(e.target.value)}
                placeholder="0x..."
                className="font-mono text-sm"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowPrivateKey(!showPrivateKey)}
              >
                {showPrivateKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Your private key will be encrypted before storage
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm text-muted-foreground">Max Leverage</label>
              <Input
                type="number"
                value={maxLeverage}
                onChange={(e) => setMaxLeverage(Number(e.target.value))}
                min={1}
                max={50}
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm text-muted-foreground">Default Leverage</label>
              <Input
                type="number"
                value={defaultLeverage}
                onChange={(e) => setDefaultLeverage(Number(e.target.value))}
                min={1}
                max={maxLeverage}
              />
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleSaveWallet}
              disabled={loading}
              className="flex-1"
            >
              {loading ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Wallet'
              )}
            </Button>
            {editing && (
              <Button
                variant="outline"
                onClick={() => {
                  setEditing(false)
                  setPrivateKey('')
                }}
              >
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
