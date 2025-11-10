import React, { useCallback, useEffect, useMemo, useState } from 'react'
import AssetCurveWithData from './AssetCurveWithData'
import HyperliquidSummary from './HyperliquidSummary'
import StrategyPanel from '@/components/portfolio/StrategyPanel'
import {
  AIDecision,
  ArenaPositionItem,
  ArenaPositionsAccount,
  getArenaPositions,
} from '@/lib/api'
import AlphaArenaFeed from './AlphaArenaFeed'
import ArenaAnalyticsFeed from './ArenaAnalyticsFeed'
import FlipNumber from './FlipNumber'
import RealtimePrice from './RealtimePrice'
import { useTradingMode } from '@/contexts/TradingModeContext'

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

function formatCurrency(value?: number | null, fractionDigits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return '$0.00'
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: Math.max(2, fractionDigits),
  })}`
}

const SUPPORTED_SYMBOLS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE'] as const

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
  const { tradingMode } = useTradingMode()
  const [selectedArenaAccount, setSelectedArenaAccount] = useState<number | 'all'>('all')
  const [globalPositionSnapshots, setGlobalPositionSnapshots] = useState<ArenaPositionsAccount[]>([])
  const [realtimeTotals, setRealtimeTotals] = useState<{
    available_cash: number
    frozen_cash: number
    positions_value: number
    total_assets: number
  } | null>(null)
  const [realtimeSymbolTotals, setRealtimeSymbolTotals] = useState<Record<string, number> | null>(null)
  const currentAccountId = overview?.account?.id ?? null

  useEffect(() => {
    let isMounted = true

    const loadGlobalSnapshots = async () => {
      try {
        const response = await getArenaPositions({ trading_mode: tradingMode })
        if (isMounted) {
          setGlobalPositionSnapshots(response.accounts ?? [])
        }
      } catch (err) {
        console.error('Failed to load global arena positions for overview:', err)
      }
    }

    loadGlobalSnapshots()
    const intervalId = setInterval(loadGlobalSnapshots, 60_000)

    return () => {
      isMounted = false
      clearInterval(intervalId)
    }
  }, [accountRefreshTrigger, tradingMode])

  useEffect(() => {
    if (!wsRef?.current) return

    const handleMessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data)
        if (message?.type === 'arena_asset_update') {
          if (message.totals) {
            setRealtimeTotals({
              available_cash: Number(message.totals.available_cash ?? 0),
              frozen_cash: Number(message.totals.frozen_cash ?? 0),
              positions_value: Number(message.totals.positions_value ?? 0),
              total_assets: Number(message.totals.total_assets ?? 0),
            })
          }
          if (message.symbols) {
            const nextSymbols: Record<string, number> = {}
            Object.entries(message.symbols).forEach(([key, value]) => {
              nextSymbols[key.toUpperCase()] = Number(value ?? 0)
            })
            setRealtimeSymbolTotals(nextSymbols)
          }
        }
      } catch {
        // Ignore non-JSON messages
      }
    }

    const ws = wsRef.current
    ws.addEventListener('message', handleMessage)

    return () => {
      ws.removeEventListener('message', handleMessage)
    }
  }, [wsRef])

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

  const accountPositionSummaries = useMemo(() => {
    const accountId = overview?.account?.id ?? null
    const aggregates = new Map<string, number>()

    positions.forEach((position) => {
      if (accountId && position.account_id && position.account_id !== accountId) {
        return
      }

      const marketValue =
        position.current_value ??
        position.market_value ??
        (position.last_price !== undefined && position.last_price !== null
          ? position.last_price * position.quantity
          : position.avg_cost * position.quantity)

      const symbol = position.symbol?.toUpperCase()
      if (!symbol || !SUPPORTED_SYMBOLS.includes(symbol as typeof SUPPORTED_SYMBOLS[number])) {
        return
      }

      const existing = aggregates.get(symbol) ?? 0
      aggregates.set(symbol, existing + (marketValue || 0))
    })

    return SUPPORTED_SYMBOLS.map((symbol) => ({
      symbol,
      marketValue: aggregates.get(symbol) ?? 0,
    }))
  }, [positions, overview?.account?.id])

  const globalPositionSummaries = useMemo(() => {
    if (!globalPositionSnapshots.length) {
      return []
    }

    const aggregates = new Map<string, number>()

    globalPositionSnapshots.forEach((snapshot) => {
      snapshot.positions.forEach((position: ArenaPositionItem) => {
        const symbol = position.symbol?.toUpperCase()
        if (!symbol || !SUPPORTED_SYMBOLS.includes(symbol as typeof SUPPORTED_SYMBOLS[number])) {
          return
        }
        const currentValue = Number(
          position.current_value ??
          position.notional ??
          0,
        )

        const existing = aggregates.get(symbol) ?? 0
        aggregates.set(symbol, existing + currentValue)
      })
    })

    return SUPPORTED_SYMBOLS.map((symbol) => ({
      symbol,
      marketValue: aggregates.get(symbol) ?? 0,
    }))
  }, [globalPositionSnapshots])

  const positionSummaries = useMemo(() => {
    if (realtimeSymbolTotals) {
      return SUPPORTED_SYMBOLS.map((symbol) => ({
        symbol,
        marketValue: realtimeSymbolTotals[symbol] ?? 0,
      }))
    }
    if (globalPositionSummaries.length > 0) {
      return globalPositionSummaries
    }
    return accountPositionSummaries
  }, [realtimeSymbolTotals, globalPositionSummaries, accountPositionSummaries])

  const accountPositionsValue = useMemo(() => {
    if (overview?.positions_value !== undefined && overview.positions_value !== null) {
      return overview.positions_value
    }
    return accountPositionSummaries.reduce((acc, position) => acc + position.marketValue, 0)
  }, [overview?.positions_value, accountPositionSummaries])

  const accountAvailableCash = overview?.account?.current_cash ?? 0
  const accountFrozenCash = overview?.account?.frozen_cash ?? 0
  const accountTotalAssets =
    overview?.total_assets ?? accountAvailableCash + accountFrozenCash + accountPositionsValue

  const aggregatedTotals = useMemo(() => {
    if (realtimeTotals) {
      return {
        availableCash: realtimeTotals.available_cash,
        frozenCash: realtimeTotals.frozen_cash,
        positionsValue: realtimeTotals.positions_value,
        totalAssets: realtimeTotals.total_assets,
      }
    }

    const hasGlobalSnapshots = globalPositionSnapshots.length > 0
    const accountsList = props.accounts ?? []
    const hasAccountsList = accountsList.length > 0

    const globalAvailableCash = hasGlobalSnapshots
      ? globalPositionSnapshots.reduce(
          (acc, snapshot) => acc + (snapshot.available_cash ?? 0),
          0,
        )
      : 0

    const globalPositionsValue = hasGlobalSnapshots
      ? globalPositionSnapshots.reduce((acc, snapshot) => {
          // Use positions_value from API if available (Hyperliquid provides accurate real-time value)
          // Otherwise fall back to summing individual position values
          const snapshotTotal = snapshot.positions_value !== undefined
            ? snapshot.positions_value
            : snapshot.positions.reduce((sum, position: ArenaPositionItem) => {
                const currentValue = Number(
                  position.current_value ?? position.notional ?? 0,
                )
                return sum + currentValue
              }, 0)
          return acc + snapshotTotal
        }, 0)
      : 0

    const globalFrozenCash = hasAccountsList
      ? accountsList.reduce(
          (acc: number, account: any) => acc + Number(account.frozen_cash ?? 0),
          0,
        )
      : 0

    if (!hasGlobalSnapshots && !hasAccountsList) {
      return {
        availableCash: accountAvailableCash,
        frozenCash: accountFrozenCash,
        positionsValue: accountPositionsValue,
        totalAssets: accountTotalAssets,
      }
    }

    const availableCashTotal = hasGlobalSnapshots ? globalAvailableCash : accountAvailableCash
    const positionsValueTotal = hasGlobalSnapshots ? globalPositionsValue : accountPositionsValue
    const frozenCashTotal = hasAccountsList ? globalFrozenCash : (hasGlobalSnapshots ? 0 : accountFrozenCash)
    const totalAssetsTotal = availableCashTotal + frozenCashTotal + positionsValueTotal

    return {
      availableCash: availableCashTotal,
      frozenCash: frozenCashTotal,
      positionsValue: positionsValueTotal,
      totalAssets: totalAssetsTotal,
    }
  }, [
    globalPositionSnapshots,
    props.accounts,
    accountAvailableCash,
    accountFrozenCash,
    accountPositionsValue,
    accountTotalAssets,
    realtimeTotals,
  ])

  if (!overview) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-muted-foreground">Loading account data...</div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col space-y-6 min-h-0">
      <div className="border border-border rounded-lg bg-card shadow-sm px-4 py-3 flex flex-col gap-4">
        <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 overflow-x-auto pb-1">
              {positionSummaries.map((position) => (
                <div
                  key={position.symbol}
                  className="flex items-center gap-3 rounded-md bg-muted/70 px-3 py-2 shadow-sm border border-border/70 w-[160px]"
                >
                  <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-muted text-[11px] font-semibold text-muted-foreground">
                    {position.symbol.slice(0, 4).toUpperCase()}
                  </span>
                  <div className="flex flex-col leading-tight">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                      {position.symbol}
                    </span>
                    <FlipNumber
                      value={position.marketValue}
                      prefix="$"
                      decimals={2}
                      className="text-sm font-semibold text-primary"
                    />
                    <RealtimePrice
                      symbol={position.symbol}
                      wsRef={wsRef}
                      className="mt-0.5"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs uppercase tracking-wide text-muted-foreground">
            <div className="flex flex-col leading-tight">
              <span>Cash Available</span>
              <FlipNumber
                value={aggregatedTotals.availableCash}
                prefix="$"
                decimals={2}
                className="text-base font-semibold text-foreground"
              />
            </div>
            <div className="flex flex-col leading-tight">
              <span>Frozen Cash</span>
              <FlipNumber
                value={aggregatedTotals.frozenCash}
                prefix="$"
                decimals={2}
                className="text-base font-semibold text-foreground"
              />
            </div>
            <div className="flex flex-col leading-tight">
              <span>Positions Value</span>
              <FlipNumber
                value={aggregatedTotals.positionsValue}
                prefix="$"
                decimals={2}
                className="text-base font-semibold text-foreground"
              />
            </div>
            <div className="flex flex-col leading-tight">
              <span>Total Assets</span>
              <FlipNumber
                value={aggregatedTotals.totalAssets}
                prefix="$"
                decimals={2}
                className="text-base font-semibold text-primary"
              />
            </div>
          </div>
      </div>

      {/* Main Content */}
      <div className={`grid gap-6 ${showAssetCurves ? 'grid-cols-5' : 'grid-cols-1'} min-h-0`}>
          {/* Asset Curves */}
          {showAssetCurves && (
            <div className="col-span-3 min-h-0 flex flex-col gap-4">
              <div className="flex-1 min-h-[320px] border border-border rounded-lg bg-card shadow-sm px-4 py-3 flex flex-col gap-4">
                <AssetCurveWithData
                  data={allAssetCurves}
                  wsRef={wsRef}
                  highlightAccountId={selectedArenaAccount}
                  onHighlightAccountChange={handleArenaAccountChange}
                />
              </div>
              <div className="border text-card-foreground shadow p-6 space-y-6">
                <HyperliquidSummary
                  accountId={overview?.account?.id}
                  refreshKey={accountRefreshTrigger}
                />
              </div>
            </div>
          )}

          {/* Tabs and Strategy Panel */}
          <div className={`${showAssetCurves ? 'col-span-2' : 'col-span-1'} overflow-hidden flex flex-col min-h-0`}>
          {/* Content Area */}
          <div className={`flex-1 h-0 min-h-0 overflow-hidden ${showStrategyPanel ? 'grid grid-cols-4 gap-4' : ''}`}>
            <div className={`${showStrategyPanel ? 'col-span-3' : 'col-span-1'} flex flex-col flex-1 min-h-0 overflow-hidden border border-border rounded-lg bg-card shadow-sm px-4 py-3 gap-4`}>
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
    </div>
  )
}
