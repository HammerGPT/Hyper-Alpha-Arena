import React, { useState } from 'react'
import AssetCurveWithData from './AssetCurveWithData'
import TradingPanel from '@/components/trading/TradingPanel'
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
  showTradingPanel?: boolean
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
    showTradingPanel = false,
  } = props
  const [selectedArenaAccount, setSelectedArenaAccount] = useState<number | 'all'>('all')

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

        {/* Tabs and Trading Panel */}
        <div className={`${showAssetCurves ? 'col-span-2' : 'col-span-1'} overflow-hidden flex flex-col min-h-0`}>
          {/* Content Area */}
          <div className={`flex-1 h-0 overflow-hidden ${showTradingPanel ? 'grid grid-cols-4 gap-4' : ''}`}>
            <div className={`${showTradingPanel ? 'col-span-3' : 'col-span-1'} h-full overflow-hidden flex flex-col`}>
              {showAssetCurves ? (
                <AlphaArenaFeed
                  refreshKey={accountRefreshTrigger}
                  wsRef={wsRef}
                  selectedAccount={selectedArenaAccount}
                  onSelectedAccountChange={setSelectedArenaAccount}
                />
              ) : (
                <ArenaAnalyticsFeed
                  refreshKey={accountRefreshTrigger}
                  selectedAccount={selectedArenaAccount}
                  onSelectedAccountChange={setSelectedArenaAccount}
                />
              )}
            </div>

            {showTradingPanel && (
              <div className="col-span-1 overflow-hidden min-h-0">
                <TradingPanel
                  onPlace={(payload) => {
                    if (wsRef?.current && wsRef.current.readyState === WebSocket.OPEN) {
                      wsRef.current.send(JSON.stringify({
                        type: 'place_order',
                        ...payload
                      }))
                    }
                  }}
                  user={overview?.account ? {
                    id: overview.account.id.toString(),
                    current_cash: overview.account.current_cash,
                    frozen_cash: overview.account.frozen_cash,
                    has_password: true
                  } : undefined}
                  positions={positions.map(p => ({
                    symbol: p.symbol,
                    market: p.market,
                    available_quantity: p.available_quantity
                  }))}
                  lastPrices={Object.fromEntries(
                    positions.map(p => [`${p.symbol}.${p.market}`, p.last_price ?? null])
                  )}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
