/**
 * WalletSelector - Hyperliquid钱包选择器组件
 *
 * 用于Trade页面，显示所有可用的Hyperliquid钱包（包括testnet和mainnet）
 * 不受全局TradingMode限制，由用户手动选择要操作的钱包
 */
import { useState, useEffect } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

interface WalletOption {
  wallet_id: number
  account_id: number
  account_name: string
  model: string | null
  wallet_address: string
  environment: 'testnet' | 'mainnet'
  is_active: boolean
  max_leverage: number
  default_leverage: number
}

interface WalletSelectorProps {
  selectedWalletId: number | null
  onSelect: (wallet: WalletOption) => void
}

export default function WalletSelector({
  selectedWalletId,
  onSelect
}: WalletSelectorProps) {
  const [wallets, setWallets] = useState<WalletOption[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadWallets()
  }, [])

  const loadWallets = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/hyperliquid/wallets/all')
      if (!response.ok) {
        throw new Error('Failed to load wallets')
      }
      const data = await response.json()
      setWallets(data)

      // 自动选择第一个active钱包
      if (data.length > 0 && !selectedWalletId) {
        const firstActive = data.find((w: WalletOption) => w.is_active)
        if (firstActive) {
          onSelect(firstActive)
        }
      }
    } catch (error) {
      console.error('Failed to load wallets:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="text-center text-muted-foreground py-4">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
        加载钱包列表...
      </div>
    )
  }

  if (wallets.length === 0) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-yellow-600 mx-auto mb-3" />
          <h3 className="font-semibold text-yellow-900 mb-2">
            系统暂无可用的Hyperliquid钱包
          </h3>
          <p className="text-sm text-yellow-800">
            请先在AI Traders管理页面为账户配置Hyperliquid钱包。<br/>
            配置完成后即可在此页面进行手动交易操作。
          </p>
        </div>
      </div>
    )
  }

  const selectedWallet = wallets.find(w => w.wallet_id === selectedWalletId)

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-muted-foreground">💼 选择交易钱包</label>
      </div>

      <select
        value={selectedWalletId || ''}
        onChange={(e) => {
          const wallet = wallets.find(w => w.wallet_id === Number(e.target.value))
          if (wallet) onSelect(wallet)
        }}
        className="w-full border border-border rounded-lg px-4 py-3 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {wallets.map(w => {
          const statusIcon = w.is_active ? '🟢' : '🔴'
          const envLabel = w.environment === 'testnet' ? 'Testnet' : 'Mainnet'
          const shortAddr = `${w.wallet_address.slice(0, 6)}...${w.wallet_address.slice(-4)}`

          return (
            <option key={w.wallet_id} value={w.wallet_id}>
              {statusIcon} {w.account_name} ({envLabel}) - {shortAddr}
            </option>
          )
        })}
      </select>

      {selectedWallet && (
        <div className="flex items-center gap-4 text-xs text-muted-foreground border-t border-border pt-3">
          <span>
            绑定AI Trader: <strong className="text-foreground">{selectedWallet.account_name}</strong>
          </span>
          <span className="flex items-center gap-1">
            环境:
            <Badge
              variant={selectedWallet.environment === 'testnet' ? 'default' : 'destructive'}
              className="uppercase text-[10px] ml-1"
            >
              {selectedWallet.environment}
            </Badge>
          </span>
          <span>
            杠杆限制: <strong className="text-foreground">{selectedWallet.max_leverage}x</strong>
          </span>
        </div>
      )}
    </div>
  )
}
