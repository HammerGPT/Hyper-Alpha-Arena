/**
 * Wallet Configuration Panel for AI Traders
 *
 * Displays and configures BOTH Testnet and Mainnet wallets for each AI Trader
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Wallet, Eye, EyeOff, CheckCircle, RefreshCw, Plus, Trash2 } from 'lucide-react'
import {
  getAccountWallet,
  configureAccountWallet,
  testWalletConnection,
  deleteAccountWallet,
} from '@/lib/hyperliquidApi'

interface WalletConfigPanelProps {
  accountId: number
  accountName: string
  onWalletConfigured?: () => void
}

interface WalletData {
  id?: number
  walletAddress?: string
  maxLeverage: number
  defaultLeverage: number
  balance?: {
    totalEquity: number
    availableBalance: number
    marginUsagePercent: number
  }
}

export default function WalletConfigPanel({
  accountId,
  accountName,
  onWalletConfigured
}: WalletConfigPanelProps) {
  const [testnetWallet, setTestnetWallet] = useState<WalletData | null>(null)
  const [mainnetWallet, setMainnetWallet] = useState<WalletData | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingTestnet, setTestingTestnet] = useState(false)
  const [testingMainnet, setTestingMainnet] = useState(false)

  // Editing states
  const [editingTestnet, setEditingTestnet] = useState(false)
  const [editingMainnet, setEditingMainnet] = useState(false)
  const [showTestnetKey, setShowTestnetKey] = useState(false)
  const [showMainnetKey, setShowMainnetKey] = useState(false)

  // Form states for testnet
  const [testnetPrivateKey, setTestnetPrivateKey] = useState('')
  const [testnetMaxLeverage, setTestnetMaxLeverage] = useState(3)
  const [testnetDefaultLeverage, setTestnetDefaultLeverage] = useState(1)

  // Form states for mainnet
  const [mainnetPrivateKey, setMainnetPrivateKey] = useState('')
  const [mainnetMaxLeverage, setMainnetMaxLeverage] = useState(3)
  const [mainnetDefaultLeverage, setMainnetDefaultLeverage] = useState(1)

  useEffect(() => {
    loadWalletInfo()
  }, [accountId])

  const loadWalletInfo = async () => {
    try {
      setLoading(true)
      const info = await getAccountWallet(accountId)

      if (info.testnetWallet) {
        setTestnetWallet(info.testnetWallet)
        setTestnetMaxLeverage(info.testnetWallet.maxLeverage)
        setTestnetDefaultLeverage(info.testnetWallet.defaultLeverage)
      } else {
        setTestnetWallet(null)
      }

      if (info.mainnetWallet) {
        setMainnetWallet(info.mainnetWallet)
        setMainnetMaxLeverage(info.mainnetWallet.maxLeverage)
        setMainnetDefaultLeverage(info.mainnetWallet.defaultLeverage)
      } else {
        setMainnetWallet(null)
      }
    } catch (error) {
      console.error('Failed to load wallet info:', error)
      toast.error('Failed to load wallet information')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveWallet = async (environment: 'testnet' | 'mainnet') => {
    const privateKey = environment === 'testnet' ? testnetPrivateKey : mainnetPrivateKey
    const maxLeverage = environment === 'testnet' ? testnetMaxLeverage : mainnetMaxLeverage
    const defaultLeverage = environment === 'testnet' ? testnetDefaultLeverage : mainnetDefaultLeverage

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
        environment
      })

      if (result.success) {
        toast.success(`${environment === 'testnet' ? 'Testnet' : 'Mainnet'} wallet configured: ${result.walletAddress.substring(0, 10)}...`)

        // Clear form
        if (environment === 'testnet') {
          setTestnetPrivateKey('')
          setEditingTestnet(false)
        } else {
          setMainnetPrivateKey('')
          setEditingMainnet(false)
        }

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

  const handleTestConnection = async (environment: 'testnet' | 'mainnet') => {
    try {
      if (environment === 'testnet') {
        setTestingTestnet(true)
      } else {
        setTestingMainnet(true)
      }

      const result = await testWalletConnection(accountId)

      if (result.success && result.connection === 'successful') {
        toast.success(`✅ ${environment === 'testnet' ? 'Testnet' : 'Mainnet'} connection successful! Balance: $${result.accountState?.totalEquity.toFixed(2)}`)
      } else {
        toast.error(`❌ Connection failed: ${result.error || 'Unknown error'}`)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Connection test failed'
      toast.error(message)
    } finally {
      if (environment === 'testnet') {
        setTestingTestnet(false)
      } else {
        setTestingMainnet(false)
      }
    }
  }

  const handleDeleteWallet = async (environment: 'testnet' | 'mainnet') => {
    const envName = environment === 'testnet' ? 'Testnet' : 'Mainnet'

    if (!confirm(`Are you sure you want to delete the ${envName} wallet? This action cannot be undone.`)) {
      return
    }

    try {
      setLoading(true)
      const result = await deleteAccountWallet(accountId, environment)

      if (result.success) {
        toast.success(`${envName} wallet deleted successfully`)
        await loadWalletInfo()
        onWalletConfigured?.()
      } else {
        toast.error('Failed to delete wallet')
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete wallet'
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  const renderWalletBlock = (
    environment: 'testnet' | 'mainnet',
    wallet: WalletData | null,
    editing: boolean,
    setEditing: (v: boolean) => void,
    privateKey: string,
    setPrivateKey: (v: string) => void,
    maxLeverage: number,
    setMaxLeverage: (v: number) => void,
    defaultLeverage: number,
    setDefaultLeverage: (v: number) => void,
    showKey: boolean,
    setShowKey: (v: boolean) => void,
    testing: boolean
  ) => {
    const envName = environment === 'testnet' ? 'Testnet' : 'Mainnet'
    const badgeVariant = environment === 'testnet' ? 'default' : 'destructive'

    return (
      <div className="p-4 border rounded-lg space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-muted-foreground" />
            <Badge variant={badgeVariant} className="text-xs">
              {environment === 'testnet' ? '🧪 TESTNET' : '💰 MAINNET'}
            </Badge>
          </div>
          {wallet && !editing && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(true)}
              >
                Edit
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleDeleteWallet(environment)}
                disabled={loading}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>

        {wallet && !editing ? (
          // Display existing wallet
          <div className="space-y-2">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Wallet Address</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-2 py-1 bg-muted rounded text-xs">
                  {wallet.walletAddress}
                </code>
                <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
              </div>
            </div>

            {wallet.balance && (
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <div className="text-muted-foreground">Balance</div>
                  <div className="font-medium">${wallet.balance.totalEquity.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Available</div>
                  <div className="font-medium">${wallet.balance.availableBalance.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Margin</div>
                  <div className="font-medium">{wallet.balance.marginUsagePercent.toFixed(1)}%</div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <div className="text-muted-foreground">Max Leverage</div>
                <div className="font-medium">{wallet.maxLeverage}x</div>
              </div>
              <div>
                <div className="text-muted-foreground">Default Leverage</div>
                <div className="font-medium">{wallet.defaultLeverage}x</div>
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTestConnection(environment)}
              disabled={testing}
              className="w-full"
            >
              {testing ? (
                <>
                  <RefreshCw className="mr-2 h-3 w-3 animate-spin" />
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
            {!wallet && (
              <div className="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs">
                <p className="text-yellow-800">
                  ⚠️ No {envName.toLowerCase()} wallet configured.
                </p>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Private Key</label>
              <div className="flex gap-2">
                <Input
                  type={showKey ? 'text' : 'password'}
                  value={privateKey}
                  onChange={(e) => setPrivateKey(e.target.value)}
                  placeholder="0x..."
                  className="font-mono text-xs h-8"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowKey(!showKey)}
                  className="h-8 px-2"
                >
                  {showKey ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Encrypted before storage
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Max Leverage</label>
                <Input
                  type="number"
                  value={maxLeverage}
                  onChange={(e) => setMaxLeverage(Number(e.target.value))}
                  min={1}
                  max={50}
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Default Leverage</label>
                <Input
                  type="number"
                  value={defaultLeverage}
                  onChange={(e) => setDefaultLeverage(Number(e.target.value))}
                  min={1}
                  max={maxLeverage}
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <div className="flex gap-2">
              <Button
                onClick={() => handleSaveWallet(environment)}
                disabled={loading}
                size="sm"
                className="flex-1 h-8 text-xs"
              >
                {loading ? (
                  <>
                    <RefreshCw className="mr-2 h-3 w-3 animate-spin" />
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
                  size="sm"
                  className="h-8 text-xs"
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

  if (loading && !testnetWallet && !mainnetWallet) {
    return (
      <div className="p-4 border rounded-lg">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Wallet className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-medium">Hyperliquid Wallets</h4>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {renderWalletBlock(
          'testnet',
          testnetWallet,
          editingTestnet,
          setEditingTestnet,
          testnetPrivateKey,
          setTestnetPrivateKey,
          testnetMaxLeverage,
          setTestnetMaxLeverage,
          testnetDefaultLeverage,
          setTestnetDefaultLeverage,
          showTestnetKey,
          setShowTestnetKey,
          testingTestnet
        )}

        {renderWalletBlock(
          'mainnet',
          mainnetWallet,
          editingMainnet,
          setEditingMainnet,
          mainnetPrivateKey,
          setMainnetPrivateKey,
          mainnetMaxLeverage,
          setMainnetMaxLeverage,
          mainnetDefaultLeverage,
          setMainnetDefaultLeverage,
          showMainnetKey,
          setShowMainnetKey,
          testingMainnet
        )}
      </div>

      <div className="text-xs text-muted-foreground bg-blue-50 border border-blue-200 rounded p-2">
        <p className="font-medium text-blue-900 mb-1">💡 Multi-Wallet Setup</p>
        <p className="text-blue-800">
          Each AI Trader can have separate wallets for testnet (paper trading) and mainnet (real funds).
          Configure both to seamlessly switch between environments without reconfiguring.
        </p>
      </div>
    </div>
  )
}
