import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  ArenaAccountMeta,
  ArenaAnalyticsAccount,
  ArenaAnalyticsSummary,
  getArenaAnalytics,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { getModelLogo } from './logoAssets'
import { formatDateTime } from '@/lib/dateTime'

interface ArenaAnalyticsFeedProps {
  refreshKey?: number
  autoRefreshInterval?: number
  selectedAccount?: number | 'all'
  onSelectedAccountChange?: (accountId: number | 'all') => void
}

type FeedTab = 'leaderboard' | 'summary' | 'advanced'

const CACHE_STALE_MS = 45_000

type CacheKey = string

interface AnalyticsCacheEntry {
  accounts: ArenaAnalyticsAccount[]
  summary: ArenaAnalyticsSummary | null
  generatedAt: string | null
  accountsMeta: ArenaAccountMeta[]
  lastFetched: number
}

const ANALYTICS_CACHE = new Map<CacheKey, AnalyticsCacheEntry>()

function formatCurrency(value?: number | null, minimumFractionDigits = 2) {
  if (value === undefined || value === null) return '—'
  return value.toLocaleString(undefined, {
    minimumFractionDigits,
    maximumFractionDigits: Math.max(minimumFractionDigits, 2),
  })
}

function formatSignedCurrency(value?: number | null) {
  if (value === undefined || value === null) return '—'
  const absolute = formatCurrency(Math.abs(value))
  const prefix = value >= 0 ? '+' : '-'
  return `${prefix}$${absolute}`
}

function formatPercent(value?: number | null, fractionDigits = 2) {
  if (value === undefined || value === null) return '—'
  return `${(value * 100).toFixed(fractionDigits)}%`
}

function formatDecimal(value?: number | null, fractionDigits = 2) {
  if (value === undefined || value === null) return '—'
  return value.toFixed(fractionDigits)
}

// Use formatDateTime from @/lib/dateTime with 'short' style for compact display
const formatDate = (value?: string | null) => formatDateTime(value, { style: 'short' })

function getTrendColor(value?: number | null) {
  if (value === undefined || value === null) return 'text-foreground'
  if (value > 0) return 'text-emerald-500'
  if (value < 0) return 'text-red-500'
  return 'text-foreground'
}

function formatMinutes(value?: number | null) {
  if (value === undefined || value === null) return '—'
  if (value < 1) return '<1m'
  const rounded = Math.round(value)
  if (rounded < 60) return `${rounded}m`
  const hours = Math.floor(rounded / 60)
  const minutes = rounded % 60
  if (minutes === 0) return `${hours}h`
  return `${hours}h ${minutes}m`
}

function buildAccountsMeta(accounts: ArenaAnalyticsAccount[]): ArenaAccountMeta[] {
  return accounts.map((account) => ({
    account_id: account.account_id,
    name: account.account_name,
    model: account.model ?? null,
  }))
}

export default function ArenaAnalyticsFeed({
  refreshKey,
  autoRefreshInterval = 60_000,
  selectedAccount: selectedAccountProp,
  onSelectedAccountChange,
}: ArenaAnalyticsFeedProps) {
  const [activeTab, setActiveTab] = useState<FeedTab>('leaderboard')
  const [analyticsAccounts, setAnalyticsAccounts] = useState<ArenaAnalyticsAccount[]>([])
  const [summary, setSummary] = useState<ArenaAnalyticsSummary | null>(null)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [accountsMeta, setAccountsMeta] = useState<ArenaAccountMeta[]>([])
  const [allTraderOptions, setAllTraderOptions] = useState<ArenaAccountMeta[]>([])
  const [internalSelectedAccount, setInternalSelectedAccount] = useState<number | 'all'>(
    selectedAccountProp ?? 'all',
  )
  const [manualRefreshKey, setManualRefreshKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const prevManualRefreshKey = useRef(manualRefreshKey)
  const prevRefreshKey = useRef(refreshKey)

  useEffect(() => {
    if (selectedAccountProp !== undefined) {
      setInternalSelectedAccount(selectedAccountProp)
    }
  }, [selectedAccountProp])

  const activeAccount = selectedAccountProp ?? internalSelectedAccount
  const cacheKey: CacheKey = activeAccount === 'all' ? 'all' : String(activeAccount)

  const primeFromCache = useCallback(
    (key: CacheKey) => {
      const cached = ANALYTICS_CACHE.get(key)
      if (!cached) return false
      setAnalyticsAccounts(cached.accounts)
      setSummary(cached.summary)
      setGeneratedAt(cached.generatedAt)
      setAccountsMeta(cached.accountsMeta)
      setLoading(false)
      return true
    },
    [],
  )

  const writeCache = useCallback(
    (key: CacheKey, entry: Partial<AnalyticsCacheEntry>) => {
      const existing = ANALYTICS_CACHE.get(key)
      ANALYTICS_CACHE.set(key, {
        accounts: entry.accounts ?? existing?.accounts ?? [],
        summary: entry.summary ?? existing?.summary ?? null,
        generatedAt: entry.generatedAt ?? existing?.generatedAt ?? null,
        accountsMeta: entry.accountsMeta ?? existing?.accountsMeta ?? [],
        lastFetched: entry.lastFetched ?? Date.now(),
      })
    },
    [],
  )

  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null
    let isMounted = true

    const shouldForce =
      manualRefreshKey !== prevManualRefreshKey.current ||
      refreshKey !== prevRefreshKey.current

    prevManualRefreshKey.current = manualRefreshKey
    prevRefreshKey.current = refreshKey

    const fetchAnalytics = async (forceReload: boolean) => {
      try {
        const cached = ANALYTICS_CACHE.get(cacheKey)
        const isFresh = cached ? Date.now() - cached.lastFetched < CACHE_STALE_MS : false
        if (!forceReload && isFresh) {
          setLoading(false)
          return
        }

        if (!cached) {
          setLoading(true)
        }
        setError(null)

        const accountId = activeAccount === 'all' ? undefined : activeAccount
        const analyticsRes = await getArenaAnalytics(
          accountId ? { account_id: accountId } : undefined,
        )

        if (!isMounted) return

        const nextAccounts = analyticsRes.accounts || []
        const nextSummary = analyticsRes.summary || null
        const nextGeneratedAt = analyticsRes.generated_at || null

        const incoming = nextAccounts.length ? buildAccountsMeta(nextAccounts) : []
        let mergedMeta: ArenaAccountMeta[] = []
        setAccountsMeta((prev) => {
          if (!incoming.length) {
            mergedMeta = prev
            return prev
          }
            const metaMap = new Map<number, ArenaAccountMeta>()
            prev.forEach((meta) => {
              metaMap.set(meta.account_id, meta)
            })
            incoming.forEach((meta) => {
              metaMap.set(meta.account_id, {
                account_id: meta.account_id,
                name: meta.name,
                model: meta.model ?? null,
              })
            })
            mergedMeta = Array.from(metaMap.values())
            return mergedMeta
        })

        // Update allTraderOptions only when viewing 'all' to preserve complete list
        if (activeAccount === 'all') {
          setAllTraderOptions((prev) => {
            const metaMap = new Map<number, ArenaAccountMeta>()
            prev.forEach((meta) => {
              metaMap.set(meta.account_id, meta)
            })
            mergedMeta.forEach((meta) => {
              metaMap.set(meta.account_id, meta)
            })
            return Array.from(metaMap.values())
          })
        }

        setAnalyticsAccounts(nextAccounts)
        setSummary(nextSummary)
        setGeneratedAt(nextGeneratedAt)

        writeCache(cacheKey, {
          accounts: nextAccounts,
          summary: nextSummary,
          generatedAt: nextGeneratedAt,
          accountsMeta: mergedMeta,
          lastFetched: Date.now(),
        })
      } catch (err) {
        console.error('Failed to load Hyper Alpha Arena analytics:', err)
        const message = err instanceof Error ? err.message : 'Failed to load analytics data'
        setError(message)
      } finally {
        setLoading(false)
      }
    }

    const hadCache = primeFromCache(cacheKey)
    if (!hadCache) {
      setLoading(true)
    }

    fetchAnalytics(shouldForce)

    if (autoRefreshInterval > 0) {
      intervalId = setInterval(() => fetchAnalytics(false), autoRefreshInterval)
    }

    return () => {
      if (intervalId) clearInterval(intervalId)
      isMounted = false
    }
  }, [
    activeAccount,
    refreshKey,
    autoRefreshInterval,
    manualRefreshKey,
    cacheKey,
    primeFromCache,
    writeCache,
  ])

  const accountOptions = useMemo(() => {
    return allTraderOptions.sort((a, b) => a.name.localeCompare(b.name))
  }, [allTraderOptions])

  const memoisedAggregates = useMemo(() => {
    const totals = analyticsAccounts.reduce(
      (acc, account) => {
        acc.tradeCount += account.trade_count || 0
        acc.decisionCount += account.decision_count || 0
        acc.executedDecisions += account.executed_decisions || 0
        return acc
      },
      { tradeCount: 0, decisionCount: 0, executedDecisions: 0 },
    )
    return totals
  }, [analyticsAccounts])

  const handleRefreshClick = () => {
    setManualRefreshKey((key) => key + 1)
  }

  const handleAccountFilterChange = (value: number | 'all') => {
    if (selectedAccountProp === undefined) {
      setInternalSelectedAccount(value)
    }
    onSelectedAccountChange?.(value)
  }

  const accountsForDisplay = analyticsAccounts

  const renderLeaderboard = () => {
    if (loading && accountsForDisplay.length === 0) {
      return <div className="text-xs text-muted-foreground">Loading leaderboard…</div>
    }
    if (!loading && accountsForDisplay.length === 0) {
      return <div className="text-xs text-muted-foreground">No analytics available yet.</div>
    }

    return accountsForDisplay.map((account, index) => {
      const rank = index + 1
      const modelLogo = getModelLogo(account.account_name || account.model)
      const pnlClass = getTrendColor(account.total_pnl)
      const returnClass = getTrendColor(account.total_return_pct)
      const sharpeClass = getTrendColor(account.sharpe_ratio)
      const winRateClass = getTrendColor(account.win_rate)

      return (
        <div
          key={account.account_id}
          className="border border-border bg-muted/40 rounded-lg px-4 py-3 space-y-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-secondary flex items-center justify-center text-sm font-semibold text-secondary-foreground">
                #{rank}
              </div>
              <div className="flex items-center gap-3">
                {modelLogo && (
                  <img
                    src={modelLogo.src}
                    alt={modelLogo.alt}
                    className="h-10 w-10 rounded-full object-contain bg-background"
                    loading="lazy"
                  />
                )}
                <div>
                  <div className="text-sm font-semibold uppercase tracking-wide text-foreground">
                    {account.account_name}
                  </div>
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {account.model || 'MODEL UNKNOWN'}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-xs uppercase tracking-wide">
              <div>
                <span className="block text-[10px] text-muted-foreground">Total P&amp;L</span>
                <span className={`font-semibold ${pnlClass}`}>{formatSignedCurrency(account.total_pnl)}</span>
                <span className={`block text-[10px] ${returnClass}`}>{formatPercent(account.total_return_pct)}</span>
              </div>
              <div>
                <span className="block text-[10px] text-muted-foreground">Total Assets</span>
                <span className="font-semibold text-foreground">${formatCurrency(account.total_assets)}</span>
              </div>
              <div>
                <span className="block text-[10px] text-muted-foreground">Fees Paid</span>
                <span className="font-semibold text-foreground">${formatCurrency(account.total_fees)}</span>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-muted-foreground">
            <div>
              <span className="block text-[10px] uppercase tracking-wide">Biggest Win</span>
              <span className="font-semibold text-foreground">{formatSignedCurrency(account.biggest_gain)}</span>
            </div>
            <div>
              <span className="block text-[10px] uppercase tracking-wide">Biggest Loss</span>
              <span className="font-semibold text-foreground">{formatSignedCurrency(account.biggest_loss)}</span>
            </div>
            <div>
              <span className="block text-[10px] uppercase tracking-wide">Sharpe</span>
              <span className={`font-semibold ${sharpeClass}`}>{formatDecimal(account.sharpe_ratio, 3)}</span>
            </div>
            <div>
              <span className="block text-[10px] uppercase tracking-wide">Win Rate</span>
              <span className={`font-semibold ${winRateClass}`}>{formatPercent(account.win_rate, 1)}</span>
            </div>
          </div>
        </div>
      )
    })
  }

  const renderSummary = () => {
    if (loading && !summary) {
      return <div className="text-xs text-muted-foreground">Loading overall statistics…</div>
    }
    if (!summary) {
      return <div className="text-xs text-muted-foreground">No summary available.</div>
    }

    const ratioClass = getTrendColor(summary.total_return_pct)
    const sharpeClass = getTrendColor(summary.average_sharpe_ratio)

    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border border-border rounded-lg bg-muted/40 p-4">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Total Assets</div>
            <div className="text-lg font-semibold text-foreground">${formatCurrency(summary.total_assets)}</div>
          </div>
          <div className="border border-border rounded-lg bg-muted/40 p-4">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Aggregate P&amp;L</div>
            <div className={`text-lg font-semibold ${getTrendColor(summary.total_pnl)}`}>
              {formatSignedCurrency(summary.total_pnl)}
            </div>
            <div className={`text-[11px] ${ratioClass}`}>{formatPercent(summary.total_return_pct)}</div>
          </div>
          <div className="border border-border rounded-lg bg-muted/40 p-4">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Total Fees</div>
            <div className="text-lg font-semibold text-foreground">${formatCurrency(summary.total_fees)}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border border-border rounded-lg bg-muted/30 p-4">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Total Volume</div>
            <div className="text-lg font-semibold text-foreground">${formatCurrency(summary.total_volume)}</div>
          </div>
          <div className="border border-border rounded-lg bg-muted/30 p-4">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Average Sharpe</div>
            <div className={`text-lg font-semibold ${sharpeClass}`}>
              {formatDecimal(summary.average_sharpe_ratio, 3)}
            </div>
          </div>
          <div className="border border-border rounded-lg bg-muted/30 p-4">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Models Tracked</div>
            <div className="text-lg font-semibold text-foreground">{accountOptions.length}</div>
          </div>
        </div>

        <div className="border border-border rounded-lg bg-muted/20 p-4 space-y-3">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Activity Snapshot</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs uppercase tracking-wide text-muted-foreground">
            <div>
              <span className="block text-[10px]">Total Trades</span>
              <span className="text-sm font-semibold text-foreground">{memoisedAggregates.tradeCount.toLocaleString()}</span>
            </div>
            <div>
              <span className="block text-[10px]">AI Decisions</span>
              <span className="text-sm font-semibold text-foreground">{memoisedAggregates.decisionCount.toLocaleString()}</span>
            </div>
            <div>
              <span className="block text-[10px]">Executed Decisions</span>
              <span className="text-sm font-semibold text-foreground">{memoisedAggregates.executedDecisions.toLocaleString()}</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const renderAdvancedAnalytics = () => {
    if (loading && accountsForDisplay.length === 0) {
      return <div className="text-xs text-muted-foreground">Loading advanced analytics…</div>
    }
    if (!loading && accountsForDisplay.length === 0) {
      return <div className="text-xs text-muted-foreground">No advanced analytics available.</div>
    }

    return accountsForDisplay.map((account) => {
      const modelLogo = getModelLogo(account.account_name || account.model)
      const executionClass = getTrendColor(account.decision_execution_rate)

      return (
        <div key={`advanced-${account.account_id}`} className="border border-border rounded-lg bg-muted/30 p-4 space-y-4">
          <div className="flex items-center gap-3">
            {modelLogo && (
              <img
                src={modelLogo.src}
                alt={modelLogo.alt}
                className="h-10 w-10 rounded-full object-contain bg-background"
                loading="lazy"
              />
            )}
            <div>
              <div className="text-sm font-semibold uppercase tracking-wide text-foreground">
                {account.account_name}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {account.model || 'MODEL UNKNOWN'}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-muted-foreground uppercase tracking-wide">
            <div className="border border-border rounded-md bg-background/40 p-3 space-y-1">
              <span className="text-[10px]">Decision Cadence</span>
              <div className="text-sm font-semibold text-foreground">
                {formatMinutes(account.avg_decision_interval_minutes)}
              </div>
              <div className="text-[10px] text-muted-foreground/80">
                First trade: {formatDate(account.first_trade_time)}
              </div>
              <div className="text-[10px] text-muted-foreground/80">
                Last trade: {formatDate(account.last_trade_time)}
              </div>
            </div>
            <div className="border border-border rounded-md bg-background/40 p-3 space-y-1">
              <span className="text-[10px]">AI Execution</span>
              <div className="text-sm font-semibold text-foreground">
                Decisions: {account.decision_count.toLocaleString()}
              </div>
              <div className={`text-[10px] font-semibold ${executionClass}`}>
                Executed: {account.executed_decisions.toLocaleString()} ({formatPercent(account.decision_execution_rate, 1)})
              </div>
              <div className="text-[10px] text-muted-foreground/80">
                Avg Target: {formatPercent(account.avg_target_portion, 1)}
              </div>
            </div>
            <div className="border border-border rounded-md bg-background/40 p-3 space-y-1">
              <span className="text-[10px]">Risk Snapshot</span>
              <div className="text-sm font-semibold text-foreground">
                Balance σ: ${formatCurrency(account.balance_volatility)}
              </div>
              <div className="text-[10px] text-muted-foreground/80">
                Biggest Win: {formatSignedCurrency(account.biggest_gain)}
              </div>
              <div className="text-[10px] text-muted-foreground/80">
                Biggest Loss: {formatSignedCurrency(account.biggest_loss)}
              </div>
            </div>
          </div>
        </div>
      )
    })
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
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>
            {activeAccount === 'all'
              ? `Tracking ${accountOptions.length} AI models`
              : 'Single model view'}
          </span>
          {generatedAt && <span className="text-muted-foreground/80">Updated {formatDate(generatedAt)}</span>}
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={handleRefreshClick}
            disabled={loading}
          >
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
          <TabsTrigger
            value="leaderboard"
            className="data-[state=active]:bg-background data-[state=active]:text-foreground border-r border-border text-[10px] md:text-xs"
          >
            LEADERBOARD
          </TabsTrigger>
          <TabsTrigger
            value="summary"
            className="data-[state=active]:bg-background data-[state=active]:text-foreground border-r border-border text-[10px] md:text-xs"
          >
            OVERALL STATS
          </TabsTrigger>
          <TabsTrigger
            value="advanced"
            className="data-[state=active]:bg-background data-[state=active]:text-foreground text-[10px] md:text-xs"
          >
            ADVANCED ANALYTICS
          </TabsTrigger>
        </TabsList>

        <div className="flex-1 border border-t-0 border-border bg-card min-h-0 flex flex-col overflow-hidden">
          {error && <div className="p-4 text-sm text-red-500">{error}</div>}

          {!error && (
            <>
              <TabsContent value="leaderboard" className="flex-1 overflow-y-auto min-h-0 mt-0 p-4 space-y-4">
                {renderLeaderboard()}
              </TabsContent>

              <TabsContent value="summary" className="flex-1 overflow-y-auto min-h-0 mt-0 p-4">
                {renderSummary()}
              </TabsContent>

              <TabsContent value="advanced" className="flex-1 overflow-y-auto min-h-0 mt-0 p-4 space-y-4">
                {renderAdvancedAnalytics()}
              </TabsContent>
            </>
          )}
        </div>
      </Tabs>
    </div>
  )
}
