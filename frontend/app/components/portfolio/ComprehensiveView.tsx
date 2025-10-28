import AccountDataView from './AccountDataView'
import { AIDecision } from '@/lib/api'

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
  loadingAccounts
}: ComprehensiveViewProps) {

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
