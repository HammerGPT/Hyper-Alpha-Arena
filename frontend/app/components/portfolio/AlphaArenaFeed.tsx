import React, { useEffect, useMemo, useState, useRef } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  ArenaAccountMeta,
  ArenaModelChatEntry,
  ArenaPositionsAccount,
  ArenaTrade,
  getArenaModelChat,
  getArenaPositions,
  getArenaTrades,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { getModelLogo, getSymbolLogo } from './logoAssets'
import FlipNumber from './FlipNumber'
import HighlightWrapper from './HighlightWrapper'

interface AlphaArenaFeedProps {
  refreshKey?: number
  autoRefreshInterval?: number
  wsRef?: React.MutableRefObject<WebSocket | null>
  selectedAccount?: number | 'all'
  onSelectedAccountChange?: (accountId: number | 'all') => void
}

type FeedTab = 'trades' | 'model-chat' | 'positions'

const DEFAULT_LIMIT = 100
const MODEL_CHAT_LIMIT = 60

function formatCurrency(value: number, minimumFractionDigits = 2) {
  return value.toLocaleString(undefined, {
    minimumFractionDigits,
    maximumFractionDigits: Math.max(minimumFractionDigits, 2),
  })
}

function formatDate(value?: string | null) {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPercent(value?: number | null) {
  if (value === undefined || value === null) return '—'
  return `${(value * 100).toFixed(2)}%`
}

function formatTriggerMode(mode?: string | null) {
  switch (mode) {
    case 'realtime':
      return 'Real-time Trigger'
    case 'interval':
      return 'Fixed Interval'
    case 'tick_batch':
      return 'Tick Batch'
    default:
      return 'Unknown Trigger Mode'
  }
}

export default function AlphaArenaFeed({
  refreshKey,
  autoRefreshInterval = 60_000,
  wsRef,
  selectedAccount: selectedAccountProp,
  onSelectedAccountChange,
}: AlphaArenaFeedProps) {
  const [activeTab, setActiveTab] = useState<FeedTab>('trades')
  const [trades, setTrades] = useState<ArenaTrade[]>([])
  const [modelChat, setModelChat] = useState<ArenaModelChatEntry[]>([])
  const [positions, setPositions] = useState<ArenaPositionsAccount[]>([])
  const [accountsMeta, setAccountsMeta] = useState<ArenaAccountMeta[]>([])
  const [internalSelectedAccount, setInternalSelectedAccount] = useState<number | 'all'>(
    selectedAccountProp ?? 'all',
  )
  const [expandedChat, setExpandedChat] = useState<number | null>(null)
  const [manualRefreshKey, setManualRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Track seen items for highlight animation
  const seenTradeIds = useRef<Set<number>>(new Set())
  const seenDecisionIds = useRef<Set<number>>(new Set())

  useEffect(() => {
    if (selectedAccountProp !== undefined) {
      setInternalSelectedAccount(selectedAccountProp)
    }
  }, [selectedAccountProp])

  const activeAccount = selectedAccountProp ?? internalSelectedAccount

  // Listen for real-time WebSocket updates
  useEffect(() => {
    if (!wsRef?.current) return

    const handleMessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data)

        // Only process messages for the active account or all accounts
        const msgAccountId = msg.trade?.account_id || msg.decision?.account_id
        const shouldProcess = activeAccount === 'all' || !msgAccountId || msgAccountId === activeAccount

        if (!shouldProcess) return

        if (msg.type === 'trade_update' && msg.trade) {
          // Prepend new trade to the list
          setTrades(prev => {
            // Check if trade already exists to prevent duplicates
            const exists = prev.some(t => t.trade_id === msg.trade.trade_id)
            if (exists) return prev
            return [msg.trade, ...prev].slice(0, DEFAULT_LIMIT)
          })
        }

        if (msg.type === 'position_update' && msg.positions) {
          // Update positions for the relevant account
          setPositions(prev => {
            // If no account_id specified in message, this is a full update for one account
            const accountId = msg.positions[0]?.account_id
            if (!accountId) return msg.positions

            // Replace positions for this specific account
            const otherAccounts = prev.filter(acc => acc.account_id !== accountId)
            // Find if we have position data in the message
            const newAccountPositions = msg.positions.filter((p: any) => p.account_id === accountId)

            if (newAccountPositions.length > 0) {
              // Construct account snapshot from positions
              const accountSnapshot = {
                account_id: accountId,
                account_name: prev.find(acc => acc.account_id === accountId)?.account_name || '',
                model: prev.find(acc => acc.account_id === accountId)?.model || null,
                available_cash: 0, // Will be updated by next snapshot
                total_unrealized_pnl: 0,
                total_return: null,
                positions: newAccountPositions
              }
              return [...otherAccounts, accountSnapshot]
            }

            return prev
          })
        }

        if (msg.type === 'model_chat_update' && msg.decision) {
          // Prepend new AI decision to the list
          setModelChat(prev => {
            // Check if decision already exists to prevent duplicates
            const exists = prev.some(entry => entry.id === msg.decision.id)
            if (exists) return prev
            return [msg.decision, ...prev].slice(0, MODEL_CHAT_LIMIT)
          })
        }
      } catch (err) {
        console.error('Failed to parse AlphaArenaFeed WebSocket message:', err)
      }
    }

    wsRef.current.addEventListener('message', handleMessage)

    return () => {
      wsRef.current?.removeEventListener('message', handleMessage)
    }
  }, [wsRef, activeAccount])

  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null

    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)

        const accountId = activeAccount === 'all' ? undefined : activeAccount

        const [tradeRes, chatRes, positionRes] = await Promise.all([
          getArenaTrades({ limit: DEFAULT_LIMIT, account_id: accountId }),
          getArenaModelChat({ limit: MODEL_CHAT_LIMIT, account_id: accountId }),
          getArenaPositions({ account_id: accountId }),
        ])

        setTrades(tradeRes.trades || [])
        setModelChat(chatRes.entries || [])
        setPositions(positionRes.accounts || [])

        const candidateMetas: ArenaAccountMeta[] = [
          ...(tradeRes.accounts || []),
          ...(positionRes.accounts || []).map((account) => ({
            account_id: account.account_id,
            name: account.account_name,
            model: account.model ?? null,
          })),
          ...(chatRes.entries || []).map((entry) => ({
            account_id: entry.account_id,
            name: entry.account_name,
            model: entry.model ?? null,
          })),
        ]

        setAccountsMeta((prev) => {
          const metaMap = new Map<number, ArenaAccountMeta>()
          prev.forEach((meta) => {
            metaMap.set(meta.account_id, meta)
          })
          candidateMetas.forEach((meta) => {
            metaMap.set(meta.account_id, {
              account_id: meta.account_id,
              name: meta.name,
              model: meta.model ?? null,
            })
          })
          return Array.from(metaMap.values())
        })
      } catch (err) {
        console.error('Failed to load Hyper Alpha Arena feed:', err)
        const message = err instanceof Error ? err.message : 'Failed to load Hyper Alpha Arena data'
        setError(message)
      } finally {
        setLoading(false)
      }
    }

    fetchData()

    if (autoRefreshInterval > 0) {
      intervalId = setInterval(fetchData, autoRefreshInterval)
    }

    return () => {
      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  }, [activeAccount, refreshKey, autoRefreshInterval, manualRefreshKey])

  const accountOptions = useMemo(() => {
    const unique = new Map<number, ArenaAccountMeta>()
    accountsMeta.forEach((meta) => {
      unique.set(meta.account_id, meta)
    })
    return Array.from(unique.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [accountsMeta])

  const handleRefreshClick = () => {
    setManualRefreshKey((key) => key + 1)
  }

  const handleAccountFilterChange = (value: number | 'all') => {
    if (selectedAccountProp === undefined) {
      setInternalSelectedAccount(value)
    }
    onSelectedAccountChange?.(value)
    setExpandedChat(null)
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Filter</span>
          <select
            value={activeAccount === 'all' ? '' : activeAccount}
            onChange={(e) => {
              const value = e.target.value
              handleAccountFilterChange(value ? Number(value) : 'all')
            }}
            className="h-8 rounded border border-border bg-muted px-2 text-xs uppercase tracking-wide text-foreground"
          >
            <option value="">All Traders</option>
            {accountOptions.map((meta) => (
              <option key={meta.account_id} value={meta.account_id}>
                {meta.name}{meta.model ? ` (${meta.model})` : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Showing last {DEFAULT_LIMIT} trades</span>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleRefreshClick} disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value: FeedTab) => setActiveTab(value)}
        className="flex-1 flex flex-col min-h-0"
      >
        <TabsList className="grid grid-cols-3 gap-0 border border-border bg-muted text-foreground">
          <TabsTrigger value="trades" className="data-[state=active]:bg-background data-[state=active]:text-foreground border-r border-border text-[10px] md:text-xs">
            COMPLETED TRADES
          </TabsTrigger>
          <TabsTrigger value="model-chat" className="data-[state=active]:bg-background data-[state=active]:text-foreground border-r border-border text-[10px] md:text-xs">
            MODELCHAT
          </TabsTrigger>
          <TabsTrigger value="positions" className="data-[state=active]:bg-background data-[state=active]:text-foreground text-[10px] md:text-xs">
            POSITIONS
          </TabsTrigger>
        </TabsList>

        <div className="flex-1 border border-t-0 border-border bg-card min-h-0 flex flex-col overflow-hidden">
          {error && (
            <div className="p-4 text-sm text-red-500">
              {error}
            </div>
          )}

          {!error && (
            <>
              <TabsContent value="trades" className="flex-1 h-0 overflow-y-auto mt-0 p-4 space-y-4">
                {loading && trades.length === 0 ? (
                  <div className="text-xs text-muted-foreground">Loading trades...</div>
                ) : trades.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No recent trades found.</div>
                ) : (
                  trades.map((trade) => {
                    const modelLogo = getModelLogo(trade.account_name || trade.model)
                    const symbolLogo = getSymbolLogo(trade.symbol)
                    const isNew = !seenTradeIds.current.has(trade.trade_id)
                    if (!seenTradeIds.current.has(trade.trade_id)) {
                      seenTradeIds.current.add(trade.trade_id)
                    }
                    return (
                      <HighlightWrapper key={`${trade.trade_id}-${trade.trade_time}`} isNew={isNew}>
                        <div className="border border-border bg-muted/40 rounded px-4 py-3 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                          <div className="flex items-center gap-2">
                            {modelLogo && (
                              <img
                                src={modelLogo.src}
                                alt={modelLogo.alt}
                                className="h-5 w-5 rounded-full object-contain bg-background"
                                loading="lazy"
                              />
                            )}
                            <span className="font-semibold text-foreground">{trade.account_name}</span>
                          </div>
                          <span>{formatDate(trade.trade_time)}</span>
                        </div>
                        <div className="text-sm text-foreground flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{trade.account_name}</span>
                          <span>completed a</span>
                          <span className="uppercase text-primary font-semibold">{trade.direction.toLowerCase()}</span>
                          <span>trade on</span>
                          <span className="flex items-center gap-2 font-semibold">
                            {symbolLogo && (
                              <img
                                src={symbolLogo.src}
                                alt={symbolLogo.alt}
                                className="h-5 w-5 rounded-full object-contain bg-background"
                                loading="lazy"
                              />
                            )}
                            {trade.symbol}
                          </span>
                          <span>!</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-muted-foreground">
                          <div>
                            <span className="block text-[10px] uppercase tracking-wide">Price</span>
                            <span className="font-medium text-foreground">
                              <FlipNumber value={trade.price} prefix="$" decimals={2} />
                            </span>
                          </div>
                          <div>
                            <span className="block text-[10px] uppercase tracking-wide">Quantity</span>
                            <span className="font-medium text-foreground">
                              <FlipNumber value={trade.quantity} decimals={4} />
                            </span>
                          </div>
                          <div>
                            <span className="block text-[10px] uppercase tracking-wide">Notional</span>
                            <span className="font-medium text-foreground">
                              <FlipNumber value={trade.notional} prefix="$" decimals={2} />
                            </span>
                          </div>
                          <div>
                            <span className="block text-[10px] uppercase tracking-wide">Commission</span>
                            <span className="font-medium text-foreground">
                              <FlipNumber value={trade.commission} prefix="$" decimals={2} />
                            </span>
                          </div>
                        </div>
                        </div>
                      </HighlightWrapper>
                    )
                  })
                )}
              </TabsContent>

              <TabsContent value="model-chat" className="flex-1 h-0 overflow-y-auto mt-0 p-4 space-y-3">
                {loading && modelChat.length === 0 ? (
                  <div className="text-xs text-muted-foreground">Loading model chat…</div>
                ) : modelChat.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No recent AI commentary.</div>
                ) : (
                  modelChat.map((entry) => {
                    const isExpanded = expandedChat === entry.id
                    const modelLogo = getModelLogo(entry.account_name || entry.model)
                    const symbolLogo = getSymbolLogo(entry.symbol || undefined)
                    const isNew = !seenDecisionIds.current.has(entry.id)
                    if (!seenDecisionIds.current.has(entry.id)) {
                      seenDecisionIds.current.add(entry.id)
                    }

                    return (
                      <HighlightWrapper key={entry.id} isNew={isNew}>
                        <button
                          type="button"
                          className="w-full text-left border border-border rounded bg-muted/30 p-4 space-y-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                          onClick={() => setExpandedChat((current) => (current === entry.id ? null : entry.id))}
                        >
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                          <div className="flex items-center gap-2">
                            {modelLogo && (
                              <img
                                src={modelLogo.src}
                                alt={modelLogo.alt}
                                className="h-5 w-5 rounded-full object-contain bg-background"
                                loading="lazy"
                              />
                            )}
                            <span className="font-semibold text-foreground">{entry.account_name}</span>
                          </div>
                          <span>{formatDate(entry.decision_time)}</span>
                        </div>
                        <div className="text-sm font-medium text-foreground">
                          {entry.operation.toUpperCase()} {entry.symbol && (
                            <span className="inline-flex items-center gap-1">
                              {symbolLogo && (
                                <img
                                  src={symbolLogo.src}
                                  alt={symbolLogo.alt}
                                  className="h-4 w-4 rounded-full object-contain bg-background"
                                  loading="lazy"
                                />
                              )}
                              {entry.symbol}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground uppercase tracking-wide">
                          <span>{formatTriggerMode(entry.trigger_mode)}</span>
                          <span>{entry.strategy_enabled ? 'Strategy Enabled' : 'Strategy Disabled'}</span>
                          {entry.last_trigger_at && (
                            <span>Last Trigger {formatDate(entry.last_trigger_at)}</span>
                          )}
                          {typeof entry.trigger_latency_seconds === 'number' && (
                            <span>Trigger Latency {entry.trigger_latency_seconds.toFixed(1)}s</span>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {isExpanded ? entry.reason : `${entry.reason.slice(0, 160)}${entry.reason.length > 160 ? '…' : ''}`}
                        </div>
                        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground uppercase tracking-wide">
                          <span>Prev Portion: <span className="font-semibold text-foreground">{(entry.prev_portion * 100).toFixed(1)}%</span></span>
                          <span>Target Portion: <span className="font-semibold text-foreground">{(entry.target_portion * 100).toFixed(1)}%</span></span>
                          <span>Total Balance: <span className="font-semibold text-foreground">
                            <FlipNumber value={entry.total_balance} prefix="$" decimals={2} />
                          </span></span>
                          <span>Executed: <span className={`font-semibold ${entry.executed ? 'text-emerald-600' : 'text-amber-600'}`}>{entry.executed ? 'YES' : 'NO'}</span></span>
                        </div>
                        <div className="mt-2 text-[11px] text-primary underline">
                          {isExpanded ? 'Click to collapse' : 'Click to expand'}
                        </div>
                        </button>
                      </HighlightWrapper>
                    )
                  })
                )}
              </TabsContent>

              <TabsContent value="positions" className="flex-1 h-0 overflow-y-auto mt-0 p-4 space-y-4">
                {loading && positions.length === 0 ? (
                  <div className="text-xs text-muted-foreground">Loading positions…</div>
                ) : positions.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No active positions currently.</div>
                ) : (
                  positions.map((snapshot) => {
                    const modelLogo = getModelLogo(snapshot.account_name || snapshot.model)
                    return (
                      <div key={snapshot.account_id} className="border border-border rounded bg-muted/40">
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
                          <div className="flex items-center gap-3">
                            {modelLogo && (
                              <img
                                src={modelLogo.src}
                                alt={modelLogo.alt}
                                className="h-6 w-6 rounded-full object-contain bg-background"
                                loading="lazy"
                              />
                            )}
                            <div>
                              <div className="text-sm font-semibold uppercase tracking-wide text-foreground">
                                {snapshot.account_name}
                              </div>
                              <div className="text-xs text-muted-foreground uppercase tracking-wide">
                                {snapshot.model || 'MODEL UNKNOWN'}
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-4 text-xs uppercase tracking-wide">
                            <div>
                              <span className="block text-[10px] text-muted-foreground">Total Unrealized P&L</span>
                              <span className={`font-semibold ${snapshot.total_unrealized_pnl >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                <FlipNumber value={snapshot.total_unrealized_pnl} prefix="$" decimals={2} />
                              </span>
                            </div>
                            <div>
                              <span className="block text-[10px] text-muted-foreground">Total Return</span>
                              <span className={`font-semibold ${snapshot.total_return && snapshot.total_return >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                {formatPercent(snapshot.total_return)}
                              </span>
                            </div>
                            <div>
                              <span className="block text-[10px] text-muted-foreground">Available Cash</span>
                              <span className="font-semibold text-foreground">
                                <FlipNumber value={snapshot.available_cash} prefix="$" decimals={2} />
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-border">
                            <thead className="bg-muted/50">
                              <tr className="text-[11px] uppercase tracking-wide text-muted-foreground">
                                <th className="px-4 py-2 text-left">Side</th>
                                <th className="px-4 py-2 text-left">Coin</th>
                                <th className="px-4 py-2 text-left">Leverage</th>
                                <th className="px-4 py-2 text-left">Notional</th>
                                <th className="px-4 py-2 text-left">Current Value</th>
                                <th className="px-4 py-2 text-left">Unreal P&L</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border text-xs text-muted-foreground">
                              {snapshot.positions.map((position) => {
                                const symbolLogo = getSymbolLogo(position.symbol)
                                return (
                                  <tr key={position.id}>
                                    <td className="px-4 py-2 font-semibold text-foreground">{position.side}</td>
                                    <td className="px-4 py-2">
                                      <div className="flex items-center gap-2 font-semibold text-foreground">
                                        {symbolLogo && (
                                          <img
                                            src={symbolLogo.src}
                                            alt={symbolLogo.alt}
                                            className="h-4 w-4 rounded-full object-contain bg-background"
                                            loading="lazy"
                                          />
                                        )}
                                        {position.symbol}
                                      </div>
                                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{position.market}</div>
                                    </td>
                                    <td className="px-4 py-2">{formatCurrency(position.quantity, 2)}</td>
                                    <td className="px-4 py-2">
                                      <FlipNumber value={position.notional} prefix="$" decimals={2} />
                                    </td>
                                    <td className="px-4 py-2">
                                      <FlipNumber value={position.current_value} prefix="$" decimals={2} />
                                    </td>
                                    <td className={`px-4 py-2 font-semibold ${position.unrealized_pnl >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                      <FlipNumber value={position.unrealized_pnl} prefix="$" decimals={2} />
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )
                  })
                )}
              </TabsContent>
            </>
          )}
        </div>
      </Tabs>
    </div>
  )
}
