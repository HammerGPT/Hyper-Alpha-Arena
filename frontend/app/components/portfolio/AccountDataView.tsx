import React, { useCallback, useEffect, useMemo, useState } from 'react'
import AssetCurveWithData from './AssetCurveWithData'
import StrategyPanel from '@/components/portfolio/StrategyPanel'
import { AIDecision } from '@/lib/api'
import AlphaArenaFeed from './AlphaArenaFeed'
import ArenaAnalyticsFeed from './ArenaAnalyticsFeed'

interface Account {
  id: number
  user_id: number
  name: string
  account_type: string
  initial_capital: number
  current_cash: number
  frozen_cash: number
}

interface Overview {
  account: Account
  total_assets: number
  positions_value: number
}

interface Position {
  id: number
  account_id?: number
  user_id?: number
  symbol: string
  name: string
  market: string
  quantity: number
  available_quantity: number
  avg_cost: number
  last_price?: number | null
  market_value?: number | null
}

interface Order {
  id: number
  order_no: string
  symbol: string
  name: string
  market: string
  side: string
  order_type: string
  price?: number
  quantity: number
  filled_quantity: number
  status: string
}

interface Trade {
  id: number
  order_id: number
  account_id?: number
  user_id?: number
  symbol: string
  name: string
  market: string
  side: string
  price: number
  quantity: number
  commission: number
  trade_time: string
}

interface AccountDataViewProps {
  overview: Overview | null
  positions: Position[]
  orders: Order[]
  trades: Trade[]
  aiDecisions: AIDecision[]
  allAssetCurves: any[]
  wsRef?: React.MutableRefObject<WebSocket | null>
  onSwitchAccount: (accountId: number) => void
  onRefreshData: () => void
  accountRefreshTrigger?: number
  showAssetCurves?: boolean
  showStrategyPanel?: boolean
  accounts?: any[]
  loadingAccounts?: boolean
}

export default function AccountDataView(props: AccountDataViewProps) {
  const {
    overview,
    positions,
    allAssetCurves,
    wsRef,
    onSwitchAccount,
    accountRefreshTrigger,
    showAssetCurves = true,
    showStrategyPanel = false,
  } = props
  const [selectedArenaAccount, setSelectedArenaAccount] = useState<number | 'all'>('all')
  const currentAccountId = overview?.account?.id ?? null

  useEffect(() => {
    if (!currentAccountId) return
    if (selectedArenaAccount === 'all') return
    if (selectedArenaAccount !== currentAccountId) {
      setSelectedArenaAccount(currentAccountId)
    }
  }, [currentAccountId, selectedArenaAccount])

  const handleArenaAccountChange = useCallback((value: number | 'all') => {
    setSelectedArenaAccount(value)
    if (value !== 'all' && currentAccountId !== value) {
      onSwitchAccount(value)
    }
  }, [onSwitchAccount, currentAccountId])

  const handleStrategyAccountChange = useCallback((accountId: number) => {
    setSelectedArenaAccount(accountId)
    if (currentAccountId !== accountId) {
      onSwitchAccount(accountId)
    }
  }, [onSwitchAccount, currentAccountId])

  const strategyAccounts = useMemo(() => {
    if (!props.accounts || props.accounts.length === 0) return []
    return props.accounts.map((account: any) => ({
      id: account.id,
      name: account.name || account.username || `Trader ${account.id}`,
      model: account.model ?? null,
    }))
  }, [props.accounts])

  if (!overview) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-muted-foreground">Loading account data...</div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col space-y-6 min-h-0">
      {/* Main Content */}
      <div className={`grid gap-6 overflow-hidden ${showAssetCurves ? 'grid-cols-5' : 'grid-cols-1'} h-full min-h-0`}>
        {/* Asset Curves */}
        {showAssetCurves && (
          <div className="col-span-3 min-h-0">
            <AssetCurveWithData
              data={allAssetCurves}
              wsRef={wsRef}
              highlightAccountId={selectedArenaAccount}
            />
          </div>
        )}

        {/* Tabs and Strategy Panel */}
        <div className={`${showAssetCurves ? 'col-span-2' : 'col-span-1'} overflow-hidden flex flex-col min-h-0`}>
          {/* Content Area */}
          <div className={`flex-1 h-0 overflow-hidden ${showStrategyPanel ? 'grid grid-cols-4 gap-4' : ''}`}>
            <div className={`${showStrategyPanel ? 'col-span-3' : 'col-span-1'} h-full overflow-hidden flex flex-col`}>
              {showAssetCurves ? (
                <AlphaArenaFeed
                  refreshKey={accountRefreshTrigger}
                  wsRef={wsRef}
                  selectedAccount={selectedArenaAccount}
                  onSelectedAccountChange={handleArenaAccountChange}
                />
              ) : (
                <ArenaAnalyticsFeed
                  refreshKey={accountRefreshTrigger}
                  selectedAccount={selectedArenaAccount}
                  onSelectedAccountChange={handleArenaAccountChange}
                />
              )}
            </div>

            {showStrategyPanel && overview?.account && (
              <div className="col-span-1 overflow-hidden min-h-0">
                <StrategyPanel
                  accountId={overview.account.id}
                  accountName={overview.account.name}
                  refreshKey={accountRefreshTrigger}
                  accounts={strategyAccounts}
                  onAccountChange={handleStrategyAccountChange}
                  accountsLoading={props.loadingAccounts}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
