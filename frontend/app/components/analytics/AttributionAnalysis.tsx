import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { AlertTriangle, Sparkles, X, Info, RefreshCw, Play } from 'lucide-react'
import AiAttributionChatModal from './AiAttributionChatModal'
import TradeReplayModal from './TradeReplayModal'
import PromptBacktest from './PromptBacktest'
import { TradingAccount, checkPnlSyncStatus, updateArenaPnl } from '@/lib/api'

// Types
interface SummaryMetrics {
  total_pnl: number
  total_fee: number
  net_pnl: number
  trade_count: number
  win_count: number
  loss_count: number
  win_rate: number
  avg_win: number | null
  avg_loss: number | null
  profit_factor: number | null
}

interface DataCompleteness {
  total_decisions: number
  with_strategy: number
  with_signal: number
  with_pnl: number
}

interface TriggerBreakdown {
  count: number
  net_pnl: number
}

interface SummaryResponse {
  period: { start: string | null; end: string | null }
  overview: SummaryMetrics
  data_completeness: DataCompleteness
  by_trigger_type: Record<string, TriggerBreakdown>
}

interface DimensionItem {
  metrics: SummaryMetrics
  by_trigger_type?: Record<string, TriggerBreakdown>
  [key: string]: unknown
}

interface DimensionResponse {
  items: DimensionItem[]
  unattributed?: { count: number; metrics: SummaryMetrics | null }
}

interface Account {
  id: number
  name: string
  account_type: string
  model?: string
}

// Trade details types
interface TradeDetail {
  id: number
  source?: 'ai' | 'program'
  symbol: string
  decision_time: string | null
  entry_time: string | null
  exit_time: string | null
  entry_type: string
  exit_type: string
  gross_pnl: number
  fees: number
  net_pnl: number
  tags: string[]
  hyperliquid_order_id: string | null
  tp_order_id: string | null
  sl_order_id: string | null
}

interface TradesResponse {
  trades: TradeDetail[]
  total: number
  limit: number
  offset: number
  account_equity: number
  loss_threshold: number
}

// API functions
const API_BASE = '/api/analytics'

async function fetchSummary(params: URLSearchParams): Promise<SummaryResponse> {
  const res = await fetch(`${API_BASE}/summary?${params}`)
  if (!res.ok) throw new Error('Failed to fetch summary')
  return res.json()
}

async function fetchByDimension(dimension: string, params: URLSearchParams): Promise<DimensionResponse> {
  const res = await fetch(`${API_BASE}/by-${dimension}?${params}`)
  if (!res.ok) throw new Error(`Failed to fetch by-${dimension}`)
  return res.json()
}

async function fetchProgramByDimension(dimension: string, params: URLSearchParams): Promise<DimensionResponse> {
  const res = await fetch(`${API_BASE}/program-by-${dimension}?${params}`)
  if (!res.ok) throw new Error(`Failed to fetch program-by-${dimension}`)
  return res.json()
}

async function fetchAccounts(): Promise<Account[]> {
  const res = await fetch('/api/account/list')
  if (!res.ok) throw new Error('Failed to fetch accounts')
  const data = await res.json()
  return data.map((acc: { id: number; name: string; account_type: string; model?: string }) => ({
    id: acc.id,
    name: acc.name,
    account_type: acc.account_type,
    model: acc.model
  }))
}

async function fetchTrades(params: URLSearchParams): Promise<TradesResponse> {
  const res = await fetch(`${API_BASE}/trades?${params}`)
  if (!res.ok) throw new Error('Failed to fetch trades')
  return res.json()
}

export default function AttributionAnalysis() {
  const { t } = useTranslation()

  // Filter states
  const [environment, setEnvironment] = useState<string>('mainnet')
  const [exchange, setExchange] = useState<string>('all')
  const [accountId, setAccountId] = useState<string>('all')
  const [timeRange, setTimeRange] = useState<string>('all')

  // Data states
  const [accounts, setAccounts] = useState<Account[]>([])
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [bySymbol, setBySymbol] = useState<DimensionResponse | null>(null)
  const [byStrategy, setByStrategy] = useState<DimensionResponse | null>(null)
  const [byTrigger, setByTrigger] = useState<DimensionResponse | null>(null)
  const [byOperation, setByOperation] = useState<DimensionResponse | null>(null)
  const [byFactor, setByFactor] = useState<DimensionResponse | null>(null)
  // Program analytics states
  const [progBySymbol, setProgBySymbol] = useState<DimensionResponse | null>(null)
  const [progByProgram, setProgByProgram] = useState<DimensionResponse | null>(null)
  const [progByTrigger, setProgByTrigger] = useState<DimensionResponse | null>(null)
  const [progByOperation, setProgByOperation] = useState<DimensionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNotice, setShowNotice] = useState(true)
  const [aiChatOpen, setAiChatOpen] = useState(false)

  // PnL sync status
  const [needsSync, setNeedsSync] = useState(false)
  const [unsyncCount, setUnsyncCount] = useState(0)
  const [syncing, setSyncing] = useState(false)

  // Trade details states
  const [activeTab, setActiveTab] = useState('dimensions')
  const [trades, setTrades] = useState<TradeDetail[]>([])
  const [tradesTotal, setTradesTotal] = useState(0)
  const [tradesLoading, setTradesLoading] = useState(false)
  const [tagFilter, setTagFilter] = useState<string | null>(null)
  const [replayOpen, setReplayOpen] = useState(false)
  const [replayTradeId, setReplayTradeId] = useState<number | null>(null)

  // Load accounts on mount
  useEffect(() => {
    fetchAccounts().then(setAccounts).catch(console.error)
  }, [])

  // Check PnL sync status when environment changes
  useEffect(() => {
    checkPnlSyncStatus(environment)
      .then(status => {
        setNeedsSync(status.needs_sync)
        setUnsyncCount(status.unsync_count)
      })
      .catch(console.error)
  }, [environment])

  // Handle PnL sync
  const handleSyncPnl = async () => {
    setSyncing(true)
    try {
      await updateArenaPnl()
      // Recheck status and reload data
      const status = await checkPnlSyncStatus(environment)
      setNeedsSync(status.needs_sync)
      setUnsyncCount(status.unsync_count)
      await loadData()
    } catch (error) {
      console.error('Failed to sync PnL:', error)
    } finally {
      setSyncing(false)
    }
  }

  // Load data when filters change
  useEffect(() => {
    loadData()
  }, [environment, exchange, accountId, timeRange])

  const buildParams = () => {
    const params = new URLSearchParams()
    params.set('environment', environment)
    params.set('exchange', exchange)
    if (accountId !== 'all') params.set('account_id', accountId)

    // Calculate date range based on timeRange
    const now = new Date()
    let startDate: Date | null = null

    if (timeRange === 'today') {
      startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    } else if (timeRange === 'week') {
      startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 7)
    } else if (timeRange === 'month') {
      startDate = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
    }

    if (startDate) {
      params.set('start_date', startDate.toISOString().split('T')[0])
      params.set('end_date', now.toISOString().split('T')[0])
    }

    return params
  }

  const loadData = async () => {
    setLoading(true)
    try {
      const params = buildParams()
      const safe = <T,>(p: Promise<T>, fallback: T): Promise<T> =>
        p.catch(() => fallback)
      const emptyDim: DimensionResponse = { items: [], unattributed: { count: 0, metrics: null } }
      const [
        summaryData, symbolData, strategyData, triggerData, operationData, factorData,
        progSymbolData, progProgramData, progTriggerData, progOperationData
      ] = await Promise.all([
        safe(fetchSummary(params), null),
        safe(fetchByDimension('symbol', params), emptyDim),
        safe(fetchByDimension('strategy', params), emptyDim),
        safe(fetchByDimension('trigger-type', params), emptyDim),
        safe(fetchByDimension('operation', params), emptyDim),
        safe(fetchByDimension('factor', params), emptyDim),
        safe(fetchProgramByDimension('symbol', params), emptyDim),
        safe(fetchProgramByDimension('program', params), emptyDim),
        safe(fetchProgramByDimension('trigger-type', params), emptyDim),
        safe(fetchProgramByDimension('operation', params), emptyDim),
      ])
      if (summaryData) setSummary(summaryData)
      setBySymbol(symbolData)
      setByStrategy(strategyData)
      setByTrigger(triggerData)
      setByOperation(operationData)
      setByFactor(factorData)
      setProgBySymbol(progSymbolData)
      setProgByProgram(progProgramData)
      setProgByTrigger(progTriggerData)
      setProgByOperation(progOperationData)
    } catch (error) {
      console.error('Failed to load analytics data:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadTrades = async (filter?: string | null) => {
    setTradesLoading(true)
    try {
      const params = buildParams()
      if (filter) params.set('tag_filter', filter)
      const data = await fetchTrades(params)
      setTrades(data.trades)
      setTradesTotal(data.total)
    } catch (error) {
      console.error('Failed to load trades:', error)
    } finally {
      setTradesLoading(false)
    }
  }

  // Load trades when tab changes to 'trades' or filter changes
  useEffect(() => {
    if (activeTab === 'trades') {
      loadTrades(tagFilter)
    }
  }, [activeTab, tagFilter, environment, exchange, accountId, timeRange])

  return (
    <div className="flex-1 p-4 space-y-4 overflow-auto">
      {/* Combined Notice (dismissible) */}
      {showNotice && (
        <div className="flex items-start gap-2 p-3 rounded-lg border border-amber-600/60 bg-amber-600/15">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500 flex-shrink-0 mt-0.5" />
          <p className="flex-1 text-sm text-amber-700 dark:text-amber-400">
            {t('attribution.notice')}
          </p>
          <button onClick={() => setShowNotice(false)} className="text-amber-600 hover:text-amber-700 dark:text-amber-500 dark:hover:text-amber-400 p-0.5">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* PnL Sync Warning */}
      {needsSync && (
        <div className="flex items-center gap-3 p-3 rounded-lg border border-orange-500/60 bg-orange-500/15">
          <RefreshCw className="h-4 w-4 text-orange-600 dark:text-orange-400 flex-shrink-0" />
          <p className="flex-1 text-sm text-orange-700 dark:text-orange-300">
            {t('attribution.syncWarning', { count: unsyncCount })}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={handleSyncPnl}
            disabled={syncing}
            className="border-orange-500/60 text-orange-700 hover:bg-orange-500/20 dark:text-orange-300"
          >
            {syncing ? (
              <>
                <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                {t('attribution.syncing', 'Syncing...')}
              </>
            ) : (
              t('attribution.syncPnl', 'Sync PnL Data')
            )}
          </Button>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div className="flex flex-wrap gap-4 items-center">
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="today">{t('attribution.today', 'Today')}</SelectItem>
              <SelectItem value="week">{t('attribution.thisWeek', 'This Week')}</SelectItem>
              <SelectItem value="month">{t('attribution.thisMonth', 'This Month')}</SelectItem>
              <SelectItem value="all">{t('attribution.allTime', 'All Time')}</SelectItem>
            </SelectContent>
          </Select>

          <Select value={exchange} onValueChange={setExchange}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('attribution.allExchanges', 'All Exchanges')}</SelectItem>
              <SelectItem value="hyperliquid">
                <span className="flex items-center gap-2">
                  <img src="/static/hyperliquid_logo.svg" alt="" className="w-4 h-4" />
                  Hyperliquid
                </span>
              </SelectItem>
              <SelectItem value="binance">
                <span className="flex items-center gap-2">
                  <img src="/static/binance_logo.svg" alt="" className="w-4 h-4" />
                  Binance
                </span>
              </SelectItem>
            </SelectContent>
          </Select>

          <Select value={environment} onValueChange={setEnvironment}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="testnet">Testnet</SelectItem>
              <SelectItem value="mainnet">Mainnet</SelectItem>
              <SelectItem value="paper">Paper</SelectItem>
            </SelectContent>
          </Select>

          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder={t('attribution.allAccounts', 'All Accounts')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('attribution.allAccounts', 'All Accounts')}</SelectItem>
              {accounts.map(acc => (
                <SelectItem key={acc.id} value={String(acc.id)}>{acc.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          size="sm"
          className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white border-0 shadow-lg hover:shadow-xl transition-all"
          onClick={() => setAiChatOpen(true)}
        >
          <Sparkles className="w-4 h-4 mr-2" />{t('attribution.aiAnalysisBtn', 'AI Attribution')}
        </Button>
      </div>

      {/* Summary Cards - placeholder */}
      {loading ? (
        <div className="text-center py-8 text-muted-foreground">Loading...</div>
      ) : (
        <>
          {/* Summary metrics will be added here */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card><CardHeader className="pb-2"><CardTitle className="text-sm">{t('attribution.grossPnl', 'Gross PnL')}</CardTitle></CardHeader><CardContent><div className={`text-2xl font-bold ${(summary?.overview.total_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>${summary?.overview.total_pnl?.toFixed(2) || '0.00'}</div></CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="text-sm">{t('attribution.totalFees', 'Total Fees')}</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold text-orange-500">${summary?.overview.total_fee?.toFixed(2) || '0.00'}</div></CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="text-sm">{t('attribution.netPnl', 'Net PnL')}</CardTitle></CardHeader><CardContent><div className={`text-2xl font-bold ${(summary?.overview.net_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>${summary?.overview.net_pnl?.toFixed(2) || '0.00'}</div></CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="text-sm">{t('attribution.aiWinRate', 'AI Win Rate')}</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{((summary?.overview.win_rate || 0) * 100).toFixed(1)}%</div></CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="text-sm">{t('attribution.tradeCount', 'Trades')}</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{summary?.overview.trade_count || 0}</div></CardContent></Card>
          </div>

          {/* Tabs for Dimension Analysis and Trade Details */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <div className="flex items-center gap-4 flex-wrap">
              <TabsList className="grid w-full grid-cols-3 max-w-lg">
                <TabsTrigger value="dimensions">{t('attribution.tabs.dimensions', 'Dimension Analysis')}</TabsTrigger>
                <TabsTrigger value="trades">{t('attribution.tabs.trades', 'Trade Details')}</TabsTrigger>
                <TabsTrigger value="backtest">{t('attribution.tabs.backtest', 'Prompt Backtest')}</TabsTrigger>
              </TabsList>
              {activeTab === 'backtest' && (
                <p className="text-xs text-muted-foreground">
                  {t('promptBacktest.description', 'Replay historical decisions with modified prompts. Placeholders are fixed.')}
                </p>
              )}
            </div>

            <TabsContent value="dimensions" className="mt-4 space-y-6">
              {/* AI Decision Section */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold border-b pb-2">{t('attribution.aiDecision', 'AI Decision')}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* By Symbol */}
            <Card>
              <CardHeader><CardTitle>{t('attribution.bySymbol', 'By Symbol')}</CardTitle></CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="text-left p-2 font-medium">Symbol</th>
                      <th className="text-right p-2 font-medium">Gross PnL</th>
                      <th className="text-right p-2 font-medium">Fees</th>
                      <th className="text-right p-2 font-medium">Net PnL</th>
                      <th className="text-right p-2 font-medium">Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bySymbol?.items.map((item: DimensionItem & { symbol?: string }) => (
                      <tr key={item.symbol} className="border-b last:border-0">
                        <td className="p-2 font-medium">{item.symbol}</td>
                        <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                        <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                        <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                        <td className="p-2 text-right">{item.metrics.trade_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* By Strategy */}
            <Card>
              <CardHeader><CardTitle>{t('attribution.byStrategy', 'By Strategy')}</CardTitle></CardHeader>
              <CardContent className="p-0">
                {byStrategy?.items.length === 0 ? (
                  <div className="text-muted-foreground text-sm p-4">{t('attribution.noStrategyData', 'No strategy attribution data')}</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="text-left p-2 font-medium">Strategy</th>
                        <th className="text-right p-2 font-medium">Gross PnL</th>
                        <th className="text-right p-2 font-medium">Fees</th>
                        <th className="text-right p-2 font-medium">Net PnL</th>
                        <th className="text-right p-2 font-medium">Trades</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byStrategy?.items.map((item: DimensionItem & { strategy_id?: number; strategy_name?: string }) => (
                        <tr key={item.strategy_id} className="border-b last:border-0">
                          <td className="p-2 font-medium">{item.strategy_name}</td>
                          <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                          <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                          <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                          <td className="p-2 text-right">{item.metrics.trade_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {byStrategy?.unattributed && byStrategy.unattributed.count > 0 && (
                  <div className="p-2 border-t text-sm text-muted-foreground">
                    {t('attribution.unattributed', 'Unattributed')}: {byStrategy.unattributed.count} trades
                  </div>
                )}
              </CardContent>
            </Card>

            {/* By Trigger Type */}
            <Card>
              <CardHeader><CardTitle>{t('attribution.byTriggerType', 'By Trigger Type')}</CardTitle></CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="text-left p-2 font-medium">Trigger</th>
                      <th className="text-right p-2 font-medium">Gross PnL</th>
                      <th className="text-right p-2 font-medium">Fees</th>
                      <th className="text-right p-2 font-medium">Net PnL</th>
                      <th className="text-right p-2 font-medium">Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byTrigger?.items.map((item: DimensionItem & { trigger_type?: string }) => (
                      <tr key={item.trigger_type} className="border-b last:border-0">
                        <td className="p-2 font-medium capitalize">{item.trigger_type}</td>
                        <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                        <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                        <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                        <td className="p-2 text-right">{item.metrics.trade_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* By Operation */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {t('attribution.byOperation', 'By Operation')}
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-4 h-4 text-muted-foreground hover:text-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-xs p-3">
                        <p className="text-sm">{t('attribution.operationTooltip')}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="text-left p-2 font-medium">Operation</th>
                      <th className="text-right p-2 font-medium">Gross PnL</th>
                      <th className="text-right p-2 font-medium">Fees</th>
                      <th className="text-right p-2 font-medium">Net PnL</th>
                      <th className="text-right p-2 font-medium">Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byOperation?.items.map((item: DimensionItem & { operation?: string }) => (
                      <tr key={item.operation} className="border-b last:border-0">
                        <td className="p-2 font-medium uppercase">{item.operation}</td>
                        <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                        <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                        <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                        <td className="p-2 text-right">{item.metrics.trade_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* By Factor */}
            {byFactor?.items && byFactor.items.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    {t('attribution.byFactor', 'By Factor')}
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Info className="w-4 h-4 text-muted-foreground hover:text-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-xs p-3">
                          <p className="text-sm">{t('attribution.byFactorTooltip')}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="text-left p-2 font-medium">Factor</th>
                        <th className="text-right p-2 font-medium">Gross PnL</th>
                        <th className="text-right p-2 font-medium">Fees</th>
                        <th className="text-right p-2 font-medium">Net PnL</th>
                        <th className="text-right p-2 font-medium">Win Rate</th>
                        <th className="text-right p-2 font-medium">Trades</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byFactor.items.map((item: DimensionItem & { factor_name?: string }) => (
                        <tr key={item.factor_name} className="border-b last:border-0">
                          <td className="p-2 font-medium font-mono">{item.factor_name}</td>
                          <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                          <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                          <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                          <td className="p-2 text-right">{item.metrics.win_rate}</td>
                          <td className="p-2 text-right">{item.metrics.trade_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}
                </div>
              </div>

              {/* Program Decision Section */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold border-b pb-2">{t('attribution.programDecision', 'Program Decision')}</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Program By Symbol */}
                  <Card>
                    <CardHeader><CardTitle>{t('attribution.bySymbol', 'By Symbol')}</CardTitle></CardHeader>
                    <CardContent className="p-0">
                      {progBySymbol?.items.length === 0 ? (
                        <div className="text-muted-foreground text-sm p-4">{t('attribution.noProgramData', 'No program execution data')}</div>
                      ) : (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-muted-foreground">
                              <th className="text-left p-2 font-medium">Symbol</th>
                              <th className="text-right p-2 font-medium">Gross PnL</th>
                              <th className="text-right p-2 font-medium">Fees</th>
                              <th className="text-right p-2 font-medium">Net PnL</th>
                              <th className="text-right p-2 font-medium">Trades</th>
                            </tr>
                          </thead>
                          <tbody>
                            {progBySymbol?.items.map((item: DimensionItem & { symbol?: string }) => (
                              <tr key={item.symbol} className="border-b last:border-0">
                                <td className="p-2 font-medium">{item.symbol}</td>
                                <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                                <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right">{item.metrics.trade_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </CardContent>
                  </Card>

                  {/* Program By Program */}
                  <Card>
                    <CardHeader><CardTitle>{t('attribution.byProgram', 'By Program')}</CardTitle></CardHeader>
                    <CardContent className="p-0">
                      {progByProgram?.items.length === 0 ? (
                        <div className="text-muted-foreground text-sm p-4">{t('attribution.noProgramData', 'No program execution data')}</div>
                      ) : (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-muted-foreground">
                              <th className="text-left p-2 font-medium">Program</th>
                              <th className="text-right p-2 font-medium">Gross PnL</th>
                              <th className="text-right p-2 font-medium">Fees</th>
                              <th className="text-right p-2 font-medium">Net PnL</th>
                              <th className="text-right p-2 font-medium">Trades</th>
                            </tr>
                          </thead>
                          <tbody>
                            {progByProgram?.items.map((item: DimensionItem & { program_id?: number; program_name?: string }) => (
                              <tr key={item.program_id} className="border-b last:border-0">
                                <td className="p-2 font-medium">{item.program_name}</td>
                                <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                                <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right">{item.metrics.trade_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                      {progByProgram?.unattributed && progByProgram.unattributed.count > 0 && (
                        <div className="p-2 border-t text-sm text-muted-foreground">
                          {t('attribution.unattributed', 'Unattributed')}: {progByProgram.unattributed.count} trades
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Program By Trigger Type */}
                  <Card>
                    <CardHeader><CardTitle>{t('attribution.byTriggerType', 'By Trigger Type')}</CardTitle></CardHeader>
                    <CardContent className="p-0">
                      {progByTrigger?.items.length === 0 ? (
                        <div className="text-muted-foreground text-sm p-4">{t('attribution.noProgramData', 'No program execution data')}</div>
                      ) : (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-muted-foreground">
                              <th className="text-left p-2 font-medium">Trigger</th>
                              <th className="text-right p-2 font-medium">Gross PnL</th>
                              <th className="text-right p-2 font-medium">Fees</th>
                              <th className="text-right p-2 font-medium">Net PnL</th>
                              <th className="text-right p-2 font-medium">Trades</th>
                            </tr>
                          </thead>
                          <tbody>
                            {progByTrigger?.items.map((item: DimensionItem & { trigger_type?: string }) => (
                              <tr key={item.trigger_type} className="border-b last:border-0">
                                <td className="p-2 font-medium capitalize">{item.trigger_type}</td>
                                <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                                <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right">{item.metrics.trade_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </CardContent>
                  </Card>

                  {/* Program By Operation */}
                  <Card>
                    <CardHeader><CardTitle>{t('attribution.byOperation', 'By Operation')}</CardTitle></CardHeader>
                    <CardContent className="p-0">
                      {progByOperation?.items.length === 0 ? (
                        <div className="text-muted-foreground text-sm p-4">{t('attribution.noProgramData', 'No program execution data')}</div>
                      ) : (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-muted-foreground">
                              <th className="text-left p-2 font-medium">Operation</th>
                              <th className="text-right p-2 font-medium">Gross PnL</th>
                              <th className="text-right p-2 font-medium">Fees</th>
                              <th className="text-right p-2 font-medium">Net PnL</th>
                              <th className="text-right p-2 font-medium">Trades</th>
                            </tr>
                          </thead>
                          <tbody>
                            {progByOperation?.items.map((item: DimensionItem & { operation?: string }) => (
                              <tr key={item.operation} className="border-b last:border-0">
                                <td className="p-2 font-medium uppercase">{item.operation}</td>
                                <td className={`p-2 text-right ${item.metrics.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.total_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right text-orange-500">${item.metrics.total_fee.toFixed(2)}</td>
                                <td className={`p-2 text-right ${item.metrics.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>${item.metrics.net_pnl.toFixed(2)}</td>
                                <td className="p-2 text-right">{item.metrics.trade_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </CardContent>
                  </Card>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="trades" className="mt-4">
              {/* Tag filter buttons */}
              <div className="flex gap-2 mb-4 flex-wrap">
                <Button
                  variant={tagFilter === null ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setTagFilter(null)}
                >
                  {t('attribution.tags.all', 'All')}
                </Button>
                <Button
                  variant={tagFilter === 'large_loss' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setTagFilter('large_loss')}
                >
                  {t('attribution.tags.largeLoss', 'Large Loss')}
                </Button>
                <Button
                  variant={tagFilter === 'sl_triggered' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setTagFilter('sl_triggered')}
                >
                  {t('attribution.tags.slTriggered', 'SL Triggered')}
                </Button>
                <Button
                  variant={tagFilter === 'consecutive_loss' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setTagFilter('consecutive_loss')}
                >
                  {t('attribution.tags.consecutiveLoss', 'Consecutive Loss')}
                </Button>
              </div>

              {/* Trade details table */}
              <Card>
                <CardContent className="p-0">
                  {tradesLoading ? (
                    <div className="text-center py-8 text-muted-foreground">Loading...</div>
                  ) : trades.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      {t('attribution.noTrades', 'No trades found')}
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-muted-foreground">
                          <th className="text-left p-2 font-medium">Symbol</th>
                          <th className="text-left p-2 font-medium">Time</th>
                          <th className="text-center p-2 font-medium">Entry</th>
                          <th className="text-center p-2 font-medium">Exit</th>
                          <th className="text-right p-2 font-medium">Gross PnL</th>
                          <th className="text-right p-2 font-medium">Fees</th>
                          <th className="text-right p-2 font-medium">Net PnL</th>
                          <th className="text-left p-2 font-medium">Tags</th>
                          <th className="text-center p-2 font-medium w-20"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map((trade) => (
                          <tr key={trade.id} className="border-b last:border-0 hover:bg-muted/50">
                            <td className="p-2 font-medium">{trade.symbol}</td>
                            <td className="p-2 text-muted-foreground text-xs">
                              <div className="flex flex-col gap-0.5">
                                <span>
                                  <span className="text-green-600 dark:text-green-400">In:</span>{' '}
                                  {trade.entry_time ? new Date(trade.entry_time + 'Z').toLocaleString() : '-'}
                                </span>
                                <span>
                                  <span className="text-red-600 dark:text-red-400">Out:</span>{' '}
                                  {trade.exit_time ? new Date(trade.exit_time + 'Z').toLocaleString() : '-'}
                                </span>
                              </div>
                            </td>
                            <td className="p-2 text-center">
                              <span className={trade.entry_type === 'BUY' ? 'text-green-500' : trade.entry_type === 'SELL' ? 'text-red-500' : ''}>
                                {trade.entry_type}
                              </span>
                            </td>
                            <td className="p-2 text-center">
                              <span className={trade.exit_type === 'TP' ? 'text-green-500' : trade.exit_type === 'SL' ? 'text-red-500' : ''}>
                                {trade.exit_type}
                              </span>
                            </td>
                            <td className={`p-2 text-right ${trade.gross_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              ${trade.gross_pnl.toFixed(2)}
                            </td>
                            <td className="p-2 text-right text-orange-500">${trade.fees.toFixed(2)}</td>
                            <td className={`p-2 text-right ${trade.net_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              ${trade.net_pnl.toFixed(2)}
                            </td>
                            <td className="p-2">
                              <div className="flex gap-1 flex-wrap">
                                {trade.tags.map((tag) => (
                                  <Badge
                                    key={tag}
                                    variant="secondary"
                                    className={
                                      tag === 'large_loss' ? 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' :
                                      tag === 'sl_triggered' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300' :
                                      tag === 'consecutive_loss' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300' :
                                      ''
                                    }
                                  >
                                    {tag === 'large_loss' ? t('attribution.tags.largeLoss', 'Large Loss') :
                                     tag === 'sl_triggered' ? t('attribution.tags.slTriggered', 'SL Triggered') :
                                     tag === 'consecutive_loss' ? t('attribution.tags.consecutiveLoss', 'Consecutive Loss') :
                                     tag}
                                  </Badge>
                                ))}
                              </div>
                            </td>
                            <td className="p-2 text-center">
                              {trade.source === 'program' ? (
                                <span className="text-xs text-muted-foreground">Program</span>
                              ) : (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="gap-1"
                                  onClick={() => {
                                    setReplayTradeId(trade.id)
                                    setReplayOpen(true)
                                  }}
                                >
                                  <Play className="h-3 w-3" />
                                  {t('attribution.replay.button', 'Replay')}
                                </Button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="backtest" className="mt-4">
              <PromptBacktest
                accountId={accountId}
                exchange={exchange}
              />
            </TabsContent>
          </Tabs>
        </>
      )}

      {/* AI Attribution Chat Modal */}
      <AiAttributionChatModal
        open={aiChatOpen}
        onOpenChange={setAiChatOpen}
        accounts={accounts as unknown as TradingAccount[]}
        accountsLoading={false}
      />

      {/* Trade Replay Modal */}
      <TradeReplayModal
        open={replayOpen}
        onOpenChange={setReplayOpen}
        tradeId={replayTradeId}
      />
    </div>
  )
}
