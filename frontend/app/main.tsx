import React, { useEffect, useRef, useState } from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import { Toaster, toast } from 'react-hot-toast'

// Global error handler for debugging
window.addEventListener('error', (event) => {
  console.error('Global error caught:', event.error)
  console.error('Error stack:', event.error?.stack)
})

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason)
})

// Create a module-level WebSocket singleton to avoid duplicate connections in React StrictMode
let __WS_SINGLETON__: WebSocket | null = null;

const resolveWsUrl = () => {
  if (typeof window === 'undefined') return 'ws://localhost:5611/ws'
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}


import Header from '@/components/layout/Header'
import Sidebar from '@/components/layout/Sidebar'
import ComprehensiveView from '@/components/portfolio/ComprehensiveView'
import SystemLogs from '@/components/layout/SystemLogs'
import PromptManager from '@/components/prompt/PromptManager'
import TraderManagement from '@/components/trader/TraderManagement'
import { HyperliquidPage } from '@/components/hyperliquid'
import HyperliquidView from '@/components/hyperliquid/HyperliquidView'
import { AIDecision, getAccounts } from '@/lib/api'
import { ArenaDataProvider } from '@/contexts/ArenaDataContext'
import { TradingModeProvider, useTradingMode } from '@/contexts/TradingModeContext'

interface User {
  id: number
  username: string
}

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
  portfolio?: {
    total_assets: number
    positions_value: number
  }
}
interface Position { id: number; account_id: number; symbol: string; name: string; market: string; quantity: number; available_quantity: number; avg_cost: number; last_price?: number | null; market_value?: number | null }
interface Order { id: number; order_no: string; symbol: string; name: string; market: string; side: string; order_type: string; price?: number; quantity: number; filled_quantity: number; status: string }
interface Trade { id: number; order_id: number; account_id: number; symbol: string; name: string; market: string; side: string; price: number; quantity: number; commission: number; trade_time: string }

const PAGE_TITLES: Record<string, string> = {
  comprehensive: 'Hyper Alpha Arena',
  'system-logs': 'System Logs',
  'prompt-management': 'Prompt Templates',
  'trader-management': 'AI Trader Management',
  'hyperliquid': 'Hyperliquid Trading',
}

function App() {
  const { tradingMode } = useTradingMode()
  const [user, setUser] = useState<User | null>(null)
  const [account, setAccount] = useState<Account | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [aiDecisions, setAiDecisions] = useState<AIDecision[]>([])
  const [allAssetCurves, setAllAssetCurves] = useState<any[]>([])
  const [hyperliquidRefreshKey, setHyperliquidRefreshKey] = useState(0)
  const [currentPage, setCurrentPage] = useState<string>('comprehensive')
  const tradingModeRef = useRef(tradingMode)

  // Temporary: Check URL hash for page routing
  useEffect(() => {
    const hash = window.location.hash.slice(1)
    if (hash && PAGE_TITLES[hash]) {
      setCurrentPage(hash)
    }
  }, [])
  const [accountRefreshTrigger, setAccountRefreshTrigger] = useState<number>(0)
  const wsRef = useRef<WebSocket | null>(null)
  const [accounts, setAccounts] = useState<any[]>([])
  const [accountsLoading, setAccountsLoading] = useState<boolean>(true)

  useEffect(() => {
    tradingModeRef.current = tradingMode
    if (tradingMode !== 'paper') {
      setHyperliquidRefreshKey(prev => prev + 1)
    }
  }, [tradingMode])

  useEffect(() => {
    let reconnectTimer: NodeJS.Timeout | null = null
    let ws = __WS_SINGLETON__
    const created = !ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED
    
    const connectWebSocket = () => {
      try {
        ws = new WebSocket(resolveWsUrl())
        __WS_SINGLETON__ = ws
        wsRef.current = ws
        
        const handleOpen = () => {
          console.log('WebSocket connected')
          // Start with hardcoded default user for paper trading
          ws!.send(JSON.stringify({
            type: 'bootstrap',
            username: 'default',
            initial_capital: 10000,
            trading_mode: tradingMode
          }))
        }
        
        const handleMessage = (e: MessageEvent) => {
          try {
            const msg = JSON.parse(e.data)
            if (msg.type === 'bootstrap_ok') {
              if (msg.user) {
                setUser(msg.user)
              }
              if (msg.account) {
                setAccount(msg.account)
                // Only request snapshot for paper mode
                if (tradingMode === 'paper') {
                  ws!.send(JSON.stringify({
                    type: 'get_snapshot',
                    trading_mode: tradingMode
                  }))
                }
              }
              // refresh accounts list once bootstrapped
              refreshAccounts()
            } else if (msg.type === 'snapshot') {
              // Process snapshot data (backend already filters by trading mode)
              if (msg.overview) setOverview(msg.overview)
              if (msg.positions) setPositions(msg.positions)
              if (msg.orders) setOrders(msg.orders)
              if (msg.trades) setTrades(msg.trades)
              if (msg.ai_decisions) setAiDecisions(msg.ai_decisions)
              if (msg.all_asset_curves) setAllAssetCurves(msg.all_asset_curves)
              const currentMode = tradingModeRef.current
              const messageMode = msg.trading_mode as string | undefined
              if (
                currentMode !== 'paper' &&
                (messageMode === undefined || messageMode === currentMode)
              ) {
                setHyperliquidRefreshKey(prev => prev + 1)
              }
            } else if (msg.type === 'trades') {
              setTrades(msg.trades || [])
            } else if (msg.type === 'order_filled') {
              toast.success('Order filled')
              const env = tradingMode === 'testnet' || tradingMode === 'mainnet' ? tradingMode : undefined
              ws!.send(JSON.stringify({
                type: 'get_snapshot',
                trading_mode: tradingMode
              }))
              ws!.send(JSON.stringify({
                type: 'get_asset_curve',
                timeframe: '5m',
                trading_mode: tradingMode,
                ...(env ? { environment: env } : {})
              }))
            } else if (msg.type === 'order_pending') {
              toast('Order placed, waiting for fill', { icon: '⏳' })
              const env = tradingMode === 'testnet' || tradingMode === 'mainnet' ? tradingMode : undefined
              ws!.send(JSON.stringify({
                type: 'get_snapshot',
                trading_mode: tradingMode
              }))
              ws!.send(JSON.stringify({
                type: 'get_asset_curve',
                timeframe: '5m',
                trading_mode: tradingMode,
                ...(env ? { environment: env } : {})
              }))
            } else if (msg.type === 'user_switched') {
              setUser(msg.user)
            } else if (msg.type === 'account_switched') {
              setAccount(msg.account)
              refreshAccounts()
            } else if (msg.type === 'trade_update') {
              // Real-time trade update - prepend to trades list
              setTrades(prev => [msg.trade, ...prev].slice(0, 100))
              toast.success('New trade executed!', { duration: 2000 })
            } else if (msg.type === 'position_update') {
              // Real-time position update
              setPositions(msg.positions || [])
            } else if (msg.type === 'model_chat_update') {
              // Real-time AI decision update - prepend to AI decisions list
              setAiDecisions(prev => [msg.decision, ...prev].slice(0, 100))
            } else if (msg.type === 'asset_curve_update') {
              // Real-time asset curve update
              setAllAssetCurves(msg.data || [])
              const currentMode = tradingModeRef.current
              const messageMode = msg.trading_mode as string | undefined
              if (
                currentMode !== 'paper' &&
                (messageMode === undefined || messageMode === currentMode)
              ) {
                setHyperliquidRefreshKey(prev => prev + 1)
              }
            } else if (msg.type === 'asset_curve_data') {
              setAllAssetCurves(msg.data || [])
              const currentMode = tradingModeRef.current
              const messageMode = msg.trading_mode as string | undefined
              if (
                currentMode !== 'paper' &&
                (messageMode === undefined || messageMode === currentMode)
              ) {
                setHyperliquidRefreshKey(prev => prev + 1)
              }
            } else if (msg.type === 'error') {
              console.error(msg.message)
              toast.error(msg.message || 'Order error')
            }
          } catch (err) {
            console.error('Failed to parse WebSocket message:', err)
          }
        }
        
        const handleClose = (event: CloseEvent) => {
          console.log('WebSocket closed:', event.code, event.reason)
          __WS_SINGLETON__ = null
          if (wsRef.current === ws) wsRef.current = null
          
          // Attempt to reconnect after 3 seconds if the close wasn't intentional
          if (event.code !== 1000 && event.code !== 1001) {
            reconnectTimer = setTimeout(() => {
              console.log('Attempting to reconnect WebSocket...')
              connectWebSocket()
            }, 3000)
          }
        }
        
        const handleError = (event: Event) => {
          console.error('WebSocket error:', event)
          // Don't show toast for every error to avoid spam
          // toast.error('Connection error')
        }

        ws.addEventListener('open', handleOpen)
        ws.addEventListener('message', handleMessage)
        ws.addEventListener('close', handleClose)
        ws.addEventListener('error', handleError)
        
        return () => {
          ws?.removeEventListener('open', handleOpen)
          ws?.removeEventListener('message', handleMessage)
          ws?.removeEventListener('close', handleClose)
          ws?.removeEventListener('error', handleError)
        }
      } catch (err) {
        console.error('Failed to create WebSocket:', err)
        // Retry connection after 5 seconds
        reconnectTimer = setTimeout(connectWebSocket, 5000)
      }
    }
    
    if (created) {
      connectWebSocket()
    } else {
      wsRef.current = ws
    }

    return () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      // Don't close the socket in cleanup to avoid issues with React StrictMode
    }
  }, [])

  // Centralized accounts fetcher
  const refreshAccounts = async () => {
    try {
      setAccountsLoading(true)
      const list = await getAccounts()
      setAccounts(list)

      // Check if user only has default account and redirect to setup
      const hasOnlyDefaultAccount = list.length === 1 &&
        list[0]?.name === "Default AI Trader" &&
        list[0]?.api_key === "default-key-please-update-in-settings"

      if (hasOnlyDefaultAccount && currentPage === 'comprehensive') {
        setCurrentPage('trader-management')
        window.location.hash = 'trader-management'
      }
    } catch (e) {
      console.error('Failed to fetch accounts', e)
    } finally {
      setAccountsLoading(false)
    }
  }

  // Fetch accounts on mount and when settings updated
  useEffect(() => {
    refreshAccounts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountRefreshTrigger])

  // Refresh data when trading mode changes
  useEffect(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && account) {
      const env = tradingMode === 'testnet' || tradingMode === 'mainnet' ? tradingMode : undefined
      wsRef.current.send(JSON.stringify({
        type: 'get_snapshot',
        trading_mode: tradingMode
      }))
      // Also refresh asset curve data
      wsRef.current.send(JSON.stringify({
        type: 'get_asset_curve',
        timeframe: '5m',
        trading_mode: tradingMode,
        ...(env ? { environment: env } : {})
      }))
    }
  }, [tradingMode, account])

  // Auto-refresh via WebSocket every 30 seconds (no console spam)
  useEffect(() => {
    const refreshInterval = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !account) {
        return
      }
      const env = tradingMode === 'testnet' || tradingMode === 'mainnet' ? tradingMode : undefined
      wsRef.current.send(JSON.stringify({
        type: 'get_snapshot',
        trading_mode: tradingMode
      }))
      wsRef.current.send(JSON.stringify({
        type: 'get_asset_curve',
        timeframe: '5m',
        trading_mode: tradingMode,
        ...(env ? { environment: env } : {})
      }))
    }, 30000)

    return () => clearInterval(refreshInterval)
  }, [account, tradingMode])

  const placeOrder = (payload: any) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WS not connected, cannot place order')
      toast.error('Not connected to server')
      return
    }
    try {
      wsRef.current.send(JSON.stringify({ type: 'place_order', ...payload }))
      toast('Placing order...', { icon: '📝' })
    } catch (e) {
      console.error(e)
      toast.error('Failed to send order')
    }
  }

  const switchUser = (username: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WS not connected, cannot switch user')
      toast.error('Not connected to server')
      return
    }
    try {
      wsRef.current.send(JSON.stringify({ type: 'switch_user', username }))
    } catch (e) {
      console.error(e)
      toast.error('Failed to switch user')
    }
  }

  const switchAccount = (accountId: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WS not connected, cannot switch account')
      toast.error('Not connected to server')
      return
    }
    try {
      wsRef.current.send(JSON.stringify({ type: 'switch_account', account_id: accountId }))
    } catch (e) {
      console.error(e)
      toast.error('Failed to switch AI trader')
    }
  }

  const handleAccountUpdated = () => {
    // Increment refresh trigger to force AccountSelector to refresh
    setAccountRefreshTrigger(prev => prev + 1)

    // Also refresh the current data snapshot
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'get_snapshot',
        trading_mode: tradingMode
      }))
    }
  }

  // For non-paper modes, create minimal state to avoid loading screen
  const effectiveOverview = overview || (tradingMode !== 'paper' ? {
    account: { id: 1, user_id: 1, name: 'Hyperliquid Account', account_type: 'AI', initial_capital: 0, current_cash: 0, frozen_cash: 0 },
    total_assets: 0,
    positions_value: 0
  } : null)

  if (!user || !account || (!effectiveOverview && tradingMode === 'paper')) return <div className="p-8">Connecting to trading server...</div>

  const renderMainContent = () => {
    const refreshData = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'get_snapshot',
          trading_mode: tradingMode
        }))
      }
    }

    return (
      <main className="flex-1 p-4 overflow-hidden flex flex-col min-h-0">

        {currentPage === 'comprehensive' && (
          tradingMode === 'paper' ? (
            <div className="flex flex-col flex-1 min-h-0 overflow-hidden pr-1">
              <ComprehensiveView
                overview={effectiveOverview}
                positions={positions}
                orders={orders}
                trades={trades}
                aiDecisions={aiDecisions}
                allAssetCurves={allAssetCurves}
                wsRef={wsRef}
                onSwitchUser={switchUser}
                onSwitchAccount={switchAccount}
                onRefreshData={refreshData}
                accountRefreshTrigger={accountRefreshTrigger}
                accounts={accounts}
                loadingAccounts={accountsLoading}
                onPageChange={setCurrentPage}
              />
            </div>
          ) : (
            <div className="flex flex-col flex-1 min-h-0">
              <HyperliquidView
                wsRef={wsRef}
                refreshKey={hyperliquidRefreshKey}
              />
            </div>
          )
        )}

        {currentPage === 'system-logs' && (
          <SystemLogs />
        )}

        {currentPage === 'prompt-management' && (
          <PromptManager />
        )}

        {currentPage === 'trader-management' && (
          <TraderManagement />
        )}

        {currentPage === 'hyperliquid' && (
          <HyperliquidPage accountId={account?.id || 1} />
        )}
      </main>
    )
  }

  const pageTitle = PAGE_TITLES[currentPage] ?? PAGE_TITLES.comprehensive

  return (
    <div className="h-screen flex overflow-hidden">
      <Sidebar
        currentPage={currentPage}
        onPageChange={setCurrentPage}
        onAccountUpdated={handleAccountUpdated}
      />
      <div className="flex-1 flex flex-col">
        <Header
          title={pageTitle}
          currentUser={user}
          currentAccount={account}
          showAccountSelector={currentPage === 'comprehensive'}
          onUserChange={switchUser}
        />
        {renderMainContent()}
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <TradingModeProvider>
      <ArenaDataProvider>
        <Toaster position="top-right" />
        <App />
      </ArenaDataProvider>
    </TradingModeProvider>
  </React.StrictMode>,
)
