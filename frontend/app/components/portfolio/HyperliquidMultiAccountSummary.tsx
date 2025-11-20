import { useEffect, useState, useMemo, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TrendingUp, AlertTriangle } from 'lucide-react'
import { getHyperliquidBalance } from '@/lib/hyperliquidApi'
import { getModelLogo } from './logoAssets'
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid'
import type { HyperliquidBalance } from '@/lib/types/hyperliquid'
import { useTradingMode } from '@/contexts/TradingModeContext'

interface AccountBalance {
  accountId: number
  accountName: string
  balance: HyperliquidBalance | null
  error: string | null
  loading: boolean
}

interface HyperliquidMultiAccountSummaryProps {
  accounts: Array<{ account_id: number; account_name: string }>
  refreshKey?: number
  selectedAccount?: number | 'all'
}

const getMarginStatus = (percent: number) => {
  if (percent < 50) {
    return {
      color: 'bg-green-500',
      text: 'Healthy',
      icon: TrendingUp,
      textColor: 'text-green-600',
      dotColor: 'bg-green-500',
    } as const
  }
  if (percent < 75) {
    return {
      color: 'bg-yellow-500',
      text: 'Moderate',
      icon: AlertTriangle,
      textColor: 'text-yellow-600',
      dotColor: 'bg-yellow-500',
    } as const
  }
  return {
    color: 'bg-red-500',
    text: 'High Risk',
    icon: AlertTriangle,
    textColor: 'text-red-600',
    dotColor: 'bg-red-500',
  } as const
}

export default function HyperliquidMultiAccountSummary({
  accounts,
  refreshKey,
  selectedAccount = 'all',
}: HyperliquidMultiAccountSummaryProps) {
  const { tradingMode } = useTradingMode()
  const [accountBalances, setAccountBalances] = useState<AccountBalance[]>([])
  const [globalLastUpdate, setGlobalLastUpdate] = useState<string | null>(null)

  // Filter accounts based on selectedAccount - memoized to prevent infinite loops
  const filteredAccounts = useMemo(() => {
    return selectedAccount === 'all'
      ? accounts
      : accounts.filter(acc => acc.account_id === selectedAccount)
  }, [accounts, selectedAccount])

  // Load all account balances in parallel - memoized to prevent infinite loops
  const loadAllBalances = useCallback(async () => {
    const results = await Promise.allSettled(
      filteredAccounts.map(async (acc) => {
        try {
          const balance = await getHyperliquidBalance(acc.account_id)
          return {
            accountId: acc.account_id,
            accountName: acc.account_name,
            balance,
            error: null,
            loading: false,
          }
        } catch (error: any) {
          console.error(`Failed to load balance for account ${acc.account_id}:`, error)
          return {
            accountId: acc.account_id,
            accountName: acc.account_name,
            balance: null,
            error: error.message || 'Failed to load',
            loading: false,
          }
        }
      })
    )

    const newBalances: AccountBalance[] = results.map((result, index) => {
      if (result.status === 'fulfilled') {
        return result.value
      } else {
        return {
          accountId: filteredAccounts[index].account_id,
          accountName: filteredAccounts[index].account_name,
          balance: null,
          error: 'Failed to load',
          loading: false,
        }
      }
    })

    setAccountBalances(newBalances)

    // Find the most recent update timestamp across all accounts
    const latestUpdate = newBalances
      .map((acc) => acc.balance?.lastUpdated)
      .filter((ts): ts is string => ts !== undefined)
      .sort()
      .reverse()[0]

    if (latestUpdate) {
      setGlobalLastUpdate(new Date(latestUpdate).toLocaleString())
    }
  }, [filteredAccounts])

  useEffect(() => {
    if (filteredAccounts.length === 0) {
      setAccountBalances([])
      return
    }

    // Only initialize with loading state on first load (when accountBalances is empty)
    const isFirstLoad = accountBalances.length === 0
    if (isFirstLoad) {
      setAccountBalances(
        filteredAccounts.map((acc) => ({
          accountId: acc.account_id,
          accountName: acc.account_name,
          balance: null,
          error: null,
          loading: true,
        }))
      )
    }

    loadAllBalances()
  }, [filteredAccounts, tradingMode, refreshKey])

  if (tradingMode !== 'testnet' && tradingMode !== 'mainnet') {
    return null
  }

  if (filteredAccounts.length === 0) {
    return (
      <Card className="p-6">
        <div className="text-sm text-muted-foreground">
          No Hyperliquid accounts configured
        </div>
      </Card>
    )
  }

  const environment: HyperliquidEnvironment =
    tradingMode === 'testnet' || tradingMode === 'mainnet' ? tradingMode : 'testnet'

  const isLoading = accountBalances.some((acc) => acc.loading)

  // Dynamic grid columns based on number of accounts
  const accountCount = accountBalances.length
  const gridColsClass = accountCount === 1
    ? 'grid-cols-1'
    : accountCount === 2
    ? 'grid-cols-1 md:grid-cols-2'
    : accountCount === 3
    ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
    : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4'

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Hyperliquid Account Status</h2>
        <Badge
          variant={environment === 'testnet' ? 'default' : 'destructive'}
          className="uppercase text-xs"
        >
          {environment}
        </Badge>
      </div>

      {globalLastUpdate && (
        <div className="text-xs text-muted-foreground -mt-2">
          Last update: {globalLastUpdate}
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="text-sm text-muted-foreground">Loading account data...</div>
      )}

      {/* Account cards grid */}
      <div className={`grid ${gridColsClass} gap-4`}>
        {accountBalances.map((account) => {
          const logo = getModelLogo(account.accountName)
          const marginStatus = account.balance
            ? getMarginStatus(account.balance.marginUsagePercent)
            : null
          const StatusIcon = marginStatus?.icon

          return (
            <Card
              key={account.accountId}
              className="p-4 space-y-3 hover:shadow-md transition-shadow"
            >
              {/* Account header with logo */}
              <div className="flex items-center gap-2 pb-2 border-b border-border">
                {logo && (
                  <img
                    src={logo.src}
                    alt={logo.alt}
                    className="h-6 w-6 rounded-full object-contain"
                  />
                )}
                <span className="font-semibold text-sm truncate">
                  {account.accountName}
                </span>
              </div>

              {/* Error state */}
              {account.error && (
                <div className="text-xs text-red-600">{account.error}</div>
              )}

              {/* Balance data */}
              {account.balance && (
                <>
                  {/* Total Equity */}
                  <div>
                    <div className="text-xs text-muted-foreground">Total Equity</div>
                    <div className="text-lg font-bold">
                      ${account.balance.totalEquity.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                  </div>

                  {/* Used Margin */}
                  <div>
                    <div className="text-xs text-muted-foreground">Used Margin</div>
                    <div className="text-sm font-medium">
                      ${account.balance.usedMargin.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                  </div>

                  {/* Margin Usage */}
                  <div>
                    <div className="text-xs text-muted-foreground">Margin Usage</div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        {account.balance.marginUsagePercent.toFixed(1)}%
                      </span>
                      {marginStatus && StatusIcon && (
                        <div className="flex items-center gap-1">
                          <span
                            className={`inline-block w-2 h-2 rounded-full ${marginStatus.dotColor}`}
                          ></span>
                          <span className={`text-xs ${marginStatus.textColor}`}>
                            {marginStatus.text}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Wallet Address */}
                  {account.balance.walletAddress && (
                    <div>
                      <div className="text-xs text-muted-foreground">Wallet</div>
                      <div className="text-xs font-mono truncate">
                        {account.balance.walletAddress.slice(0, 6)}...
                        {account.balance.walletAddress.slice(-4)}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Loading state for individual card */}
              {account.loading && (
                <div className="text-xs text-muted-foreground">Loading...</div>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}