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

interface PortfolioProps {
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
  accounts?: any[]
  loadingAccounts?: boolean
}

export default function Portfolio({
  overview,
  positions,
  orders,
  trades,
  aiDecisions,
  allAssetCurves,
  wsRef,
  onSwitchAccount,
  onRefreshData,
  accountRefreshTrigger,
  accounts,
  loadingAccounts
}: PortfolioProps) {
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
      showAssetCurves={false}
      showStrategyPanel={true}
    />
  )
}
