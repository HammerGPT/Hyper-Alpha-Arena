import { useState, useEffect } from 'react'
import AccountDataView from './AccountDataView'
import { AIDecision } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

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

interface ComprehensiveViewProps {
  overview: Overview | null
  positions: Position[]
  orders: Order[]
  trades: Trade[]
  aiDecisions: AIDecision[]
  allAssetCurves: any[]
  wsRef?: React.MutableRefObject<WebSocket | null>
  onSwitchUser: (username: string) => void
  onSwitchAccount: (accountId: number) => void
  onRefreshData: () => void
  accountRefreshTrigger?: number
  accounts?: any[]
  loadingAccounts?: boolean
  onPageChange?: (page: string) => void
}

export default function ComprehensiveView({
  overview,
  positions,
  orders,
  trades,
  aiDecisions,
  allAssetCurves,
  wsRef,
  onSwitchUser,
  onSwitchAccount,
  onRefreshData,
  accountRefreshTrigger,
  accounts,
  loadingAccounts,
  onPageChange
}: ComprehensiveViewProps) {
  const [showWelcome, setShowWelcome] = useState(false)

  useEffect(() => {
    // Check if there are no AI traders
    if (accounts && accounts.length === 0 && !loadingAccounts) {
      setShowWelcome(true)
    } else {
      setShowWelcome(false)
    }
  }, [accounts, loadingAccounts])

  if (showWelcome) {
    return (
      <div className="h-full flex items-center justify-center">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Welcome to Hyper Alpha Arena</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-muted-foreground">
              Get started by creating your first AI trader to begin automated crypto trading.
            </p>
            <div className="flex gap-2">
              <Button
                onClick={() => onPageChange?.('trader-management')}
                className="flex-1"
              >
                Setup AI Trader
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowWelcome(false)}
                className="flex-1"
              >
                Skip
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <AccountDataView
      overview={overview}
      positions={positions}
      orders={orders}
      trades={trades}
      aiDecisions={aiDecisions}
      allAssetCurves={allAssetCurves}
      wsRef={wsRef}
      onSwitchAccount={onSwitchAccount}
      onRefreshData={onRefreshData}
      accountRefreshTrigger={accountRefreshTrigger}
      accounts={accounts}
      loadingAccounts={loadingAccounts}
      showAssetCurves={true}
      showStrategyPanel={false}
    />
  )
}
