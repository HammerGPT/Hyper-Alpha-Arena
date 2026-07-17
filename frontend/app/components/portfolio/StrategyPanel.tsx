import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  getHyperliquidAvailableSymbols,
  getHyperliquidWatchlist,
  updateHyperliquidWatchlist,
} from '@/lib/api'
import type { HyperliquidSymbolMeta } from '@/lib/api'
import { formatDateTime } from '@/lib/dateTime'
import { useTranslation } from 'react-i18next'

interface StrategyConfig {
  price_threshold: number
  interval_seconds: number
  enabled: boolean
  scheduled_trigger_enabled: boolean
  last_trigger_at?: string | null
  signal_pool_id?: number | null  // Deprecated: for backward compatibility
  signal_pool_ids?: number[] | null  // New: multiple signal pools
  signal_pool_name?: string | null  // Deprecated
  signal_pool_names?: string[] | null  // New: multiple pool names
  exchange?: string  // "hyperliquid" or "binance"
  execution_mode?: string  // "real" or "paper"
  // Response-only: account-level auto-trading pause switch (separate from `enabled`,
  // which is this strategy's own flag). Never sent back on PUT.
  auto_trading_enabled?: boolean
}

interface SignalPool {
  id: number
  pool_name: string
  signal_ids: number[]
  symbols: string[]
  enabled: boolean
  logic?: string
  exchange?: string
  source_type?: string | null
}

interface GlobalSamplingConfig {
  sampling_interval: number
}

interface StrategyPanelProps {
  accountId: number
  accountName: string
  refreshKey?: number
  accounts?: Array<{ id: number; name: string; model?: string | null }>
  onAccountChange?: (accountId: number) => void
  accountsLoading?: boolean
}

// Use formatDateTime from @/lib/dateTime
function formatTimestamp(value?: string | null): string {
  if (!value) return 'No executions yet'
  return formatDateTime(value, { style: 'short' })
}

export default function StrategyPanel({
  accountId,
  accountName,
  refreshKey,
  accounts,
  onAccountChange,
  accountsLoading = false,
}: StrategyPanelProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Trader-specific settings
  const [priceThreshold, setPriceThreshold] = useState<string>('1.0')
  const [triggerInterval, setTriggerInterval] = useState<string>('150')
  const [enabled, setEnabled] = useState<boolean>(true)
  const [autoTradingEnabled, setAutoTradingEnabled] = useState<boolean>(true)
  const [scheduledTriggerEnabled, setScheduledTriggerEnabled] = useState<boolean>(true)
  const [lastTriggerAt, setLastTriggerAt] = useState<string | null>(null)
  const [signalPoolIds, setSignalPoolIds] = useState<number[]>([])
  const [signalPools, setSignalPools] = useState<SignalPool[]>([])
  const [exchange, setExchange] = useState<string>('hyperliquid')
  const [executionMode, setExecutionMode] = useState<string>('real')

  // Global settings
  const [samplingInterval, setSamplingInterval] = useState<string>('18')
  const [availableWatchlistSymbols, setAvailableWatchlistSymbols] = useState<HyperliquidSymbolMeta[]>([])
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([])
  const [watchlistLoading, setWatchlistLoading] = useState(true)
  const [watchlistSaving, setWatchlistSaving] = useState(false)
  const [watchlistError, setWatchlistError] = useState<string | null>(null)
  const [watchlistSuccess, setWatchlistSuccess] = useState<string | null>(null)
  const [maxWatchlistSymbols, setMaxWatchlistSymbols] = useState<number>(10)

  const resetMessages = useCallback(() => {
    setError(null)
    setSuccess(null)
  }, [])

  const resetWatchlistMessages = useCallback(() => {
    setWatchlistError(null)
    setWatchlistSuccess(null)
  }, [])

  const fetchStrategy = useCallback(async () => {
    setLoading(true)
    resetMessages()
    try {
      // Fetch trader-specific config and signal pools in parallel
      const [strategyResponse, signalsResponse, globalResponse] = await Promise.all([
        fetch(`/api/account/${accountId}/strategy`),
        fetch('/api/signals'),
        fetch('/api/config/global-sampling'),
      ])

      if (strategyResponse.ok) {
        const strategy: StrategyConfig = await strategyResponse.json()
        setPriceThreshold((strategy.price_threshold ?? 1.0).toString())
        setTriggerInterval((strategy.interval_seconds ?? 150).toString())
        setEnabled(strategy.enabled)
        setAutoTradingEnabled(strategy.auto_trading_enabled ?? true)
        setScheduledTriggerEnabled(strategy.scheduled_trigger_enabled ?? true)
        setLastTriggerAt(strategy.last_trigger_at ?? null)
        // Use new signal_pool_ids field, fallback to old signal_pool_id for compatibility
        const poolIds = strategy.signal_pool_ids ?? (strategy.signal_pool_id ? [strategy.signal_pool_id] : [])
        setSignalPoolIds(poolIds)
        setExchange(strategy.exchange ?? 'hyperliquid')
        setExecutionMode(strategy.execution_mode ?? 'real')
      }

      if (signalsResponse.ok) {
        const data = await signalsResponse.json()
        const pools: SignalPool[] = data.pools || []
        // Only show enabled signal pools
        setSignalPools(pools.filter((p) => p.enabled))
      }

      if (globalResponse.ok) {
        const globalConfig: GlobalSamplingConfig = await globalResponse.json()
        setSamplingInterval((globalConfig.sampling_interval ?? 18).toString())
      }
    } catch (err) {
      console.error('Failed to load strategy config', err)
      setError(err instanceof Error ? err.message : 'Unable to load strategy configuration.')
    } finally {
      setLoading(false)
    }
  }, [accountId, resetMessages])

  const fetchWatchlistConfig = useCallback(async () => {
    resetWatchlistMessages()
    setWatchlistLoading(true)
    try {
      const [available, watchlist] = await Promise.all([
        getHyperliquidAvailableSymbols(),
        getHyperliquidWatchlist(),
      ])
      setAvailableWatchlistSymbols(available.symbols || [])
      setMaxWatchlistSymbols(watchlist.max_symbols ?? available.max_symbols ?? 10)
      setWatchlistSymbols(watchlist.symbols || [])
    } catch (err) {
      console.error('Failed to load Hyperliquid watchlist', err)
      setWatchlistError(err instanceof Error ? err.message : 'Unable to load Hyperliquid watchlist.')
    } finally {
      setWatchlistLoading(false)
    }
  }, [resetWatchlistMessages])
  useEffect(() => {
    fetchStrategy()
  }, [fetchStrategy, refreshKey])

  useEffect(() => {
    fetchWatchlistConfig()
  }, [fetchWatchlistConfig, refreshKey])

  const accountOptions = useMemo(() => {
    if (!accounts || accounts.length === 0) return []
    return accounts.map((account) => ({
      value: account.id.toString(),
      label: `${account.name}${account.model ? ` (${account.model})` : ''}`,
    }))
  }, [accounts])

  const selectedAccountLabel = useMemo(() => {
    const match = accountOptions.find((option) => option.value === accountId.toString())
    return match?.label ?? accountName
  }, [accountOptions, accountId, accountName])

  const watchlistCount = watchlistSymbols.length

  useEffect(() => {
    resetMessages()
  }, [accountId, resetMessages])

  const toggleWatchlistSymbol = useCallback(
    (symbol: string) => {
      const symbolUpper = symbol.toUpperCase()
      resetWatchlistMessages()
      setWatchlistSymbols((prev) => {
        if (prev.includes(symbolUpper)) {
          return prev.filter((entry) => entry !== symbolUpper)
        }
        if (prev.length >= maxWatchlistSymbols) {
          setWatchlistError(`You can monitor up to ${maxWatchlistSymbols} symbols.`)
          return prev
        }
        return [...prev, symbolUpper]
      })
    },
    [maxWatchlistSymbols, resetWatchlistMessages]
  )

  const handleSaveWatchlist = useCallback(async () => {
    resetWatchlistMessages()
    if (watchlistSymbols.length < 1) {
      setWatchlistError('At least one symbol must be selected.')
      return
    }
    try {
      setWatchlistSaving(true)
      const response = await updateHyperliquidWatchlist(watchlistSymbols)
      setWatchlistSymbols(response.symbols || [])
      setMaxWatchlistSymbols(response.max_symbols ?? maxWatchlistSymbols)
      setWatchlistSuccess('Watchlist updated successfully.')
    } catch (err) {
      console.error('Failed to update Hyperliquid watchlist', err)
      setWatchlistError(err instanceof Error ? err.message : 'Failed to update Hyperliquid watchlist.')
    } finally {
      setWatchlistSaving(false)
    }
  }, [watchlistSymbols, maxWatchlistSymbols, resetWatchlistMessages])

  const handleSaveTrader = useCallback(async () => {
    resetMessages()

    const threshold = parseFloat(priceThreshold)
    const interval = parseInt(triggerInterval)

    if (!Number.isFinite(threshold) || threshold <= 0) {
      setError('Price threshold must be a positive number.')
      return
    }

    if (!Number.isInteger(interval) || interval <= 0) {
      setError('Trigger interval must be a positive integer.')
      return
    }

    try {
      setSaving(true)
      const payload = {
        price_threshold: threshold,
        interval_seconds: interval,
        enabled: enabled,
        scheduled_trigger_enabled: scheduledTriggerEnabled,
        trigger_mode: "unified",
        tick_batch_size: 1,
        signal_pool_ids: signalPoolIds.length > 0 ? signalPoolIds : null,
        exchange: exchange,
        execution_mode: executionMode,
      }
      console.log('Frontend saving payload:', payload)
      const response = await fetch(`/api/account/${accountId}/strategy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        throw new Error('Failed to save trader configuration')
      }

      const result: StrategyConfig = await response.json()
      setPriceThreshold((result.price_threshold ?? 1.0).toString())
      setTriggerInterval((result.interval_seconds ?? 150).toString())
      setEnabled(result.enabled)
      setAutoTradingEnabled(result.auto_trading_enabled ?? true)
      setScheduledTriggerEnabled(result.scheduled_trigger_enabled ?? true)
      setLastTriggerAt(result.last_trigger_at ?? null)
      // Use new signal_pool_ids field
      const poolIds = result.signal_pool_ids ?? (result.signal_pool_id ? [result.signal_pool_id] : [])
      setSignalPoolIds(poolIds)
      setExchange(result.exchange ?? 'hyperliquid')
      setExecutionMode(result.execution_mode ?? 'real')

      setSuccess('Trader configuration saved successfully.')
    } catch (err) {
      console.error('Failed to update trader config', err)
      setError(err instanceof Error ? err.message : 'Failed to save trader configuration.')
    } finally {
      setSaving(false)
    }
  }, [accountId, priceThreshold, triggerInterval, enabled, scheduledTriggerEnabled, signalPoolIds, exchange, executionMode, resetMessages])

  const handleSaveGlobal = useCallback(async () => {
    resetMessages()

    const interval = parseInt(samplingInterval)

    if (!Number.isInteger(interval) || interval <= 0) {
      setError('Sampling interval must be a positive integer.')
      return
    }

    try {
      setSaving(true)
      const response = await fetch('/api/config/global-sampling', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sampling_interval: interval,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to save global configuration')
      }

      const result: GlobalSamplingConfig = await response.json()
      setSamplingInterval((result.sampling_interval ?? 18).toString())

      setSuccess('Global configuration saved successfully.')
    } catch (err) {
      console.error('Failed to update global config', err)
      setError(err instanceof Error ? err.message : 'Failed to save global configuration.')
    } finally {
      setSaving(false)
    }
  }, [samplingInterval, resetMessages])

  return (
    <div className="h-full flex flex-col">
      <p className="text-sm text-muted-foreground mb-4">{t('strategy.description', 'Configure trigger parameters and Hyperliquid watchlist')}</p>
      <Tabs defaultValue="strategy" className="flex flex-col h-full flex-1 overflow-hidden">
          <TabsList className="grid grid-cols-3 max-w-2xl mb-4">
            <TabsTrigger value="strategy">{t('strategy.aiStrategy', 'AI Strategy')}</TabsTrigger>
            <TabsTrigger value="watchlist">{t('strategy.symbolWatchlist', 'Symbol Watchlist')}</TabsTrigger>
            <TabsTrigger value="global">{t('strategy.globalConfig', 'Global Configuration')}</TabsTrigger>
          </TabsList>
          <TabsContent value="strategy" className="flex-1 overflow-y-auto space-y-6">
            {loading ? (
              <div className="text-sm text-muted-foreground">{t('strategy.loadingStrategy', 'Loading strategy…')}</div>
            ) : (
              <>
            {/* Trader Selection */}
            <section className="space-y-2">
              <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.selectTrader', 'Select Trader')}</div>
              {accountOptions.length > 0 ? (
                <Select
                  value={accountId.toString()}
                  onValueChange={(value) => {
                    const nextId = Number(value)
                    if (!Number.isFinite(nextId) || nextId === accountId) {
                      return
                    }
                    resetMessages()
                    onAccountChange?.(nextId)
                  }}
                  disabled={accountsLoading}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={accountsLoading ? t('strategy.loadingTraders', 'Loading traders…') : t('strategy.selectAiTrader', 'Select AI trader')} />
                  </SelectTrigger>
                  <SelectContent>
                    {accountOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div className="text-sm text-muted-foreground">{accountName}</div>
              )}
            </section>

            {/* Trader Configuration */}
            <Card className="border-muted">
              <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                  <div className="flex flex-col space-y-1.5">
                    <CardTitle className="text-base">{t('strategy.traderConfig', 'Trader Configuration')}</CardTitle>
                    <CardDescription className="text-xs">{t('strategy.settingsFor', 'Settings for')} {selectedAccountLabel}</CardDescription>
                  </div>
                  <div className="flex flex-col space-y-1">
                    {error && <div className="text-sm text-destructive">{error}</div>}
                    {success && <div className="text-sm text-green-500">{success}</div>}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Exchange Selection */}
                <section className="space-y-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.exchange', 'Exchange')}</div>
                  <Select value={exchange} onValueChange={(value) => { setExchange(value); resetMessages() }}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('strategy.selectExchange', 'Select exchange')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hyperliquid">{t('strategy.exchangeHyperliquid', 'Hyperliquid')}</SelectItem>
                      <SelectItem value="binance">{t('strategy.exchangeBinance', 'Binance')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">{t('strategy.exchangeHint', 'Select exchange for market data and trade execution')}</p>
                </section>

                <div className="space-y-1.5">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">
                    {t('strategy.executionMode', 'Execution Mode')}
                  </div>
                  <Select value={executionMode} onValueChange={(value) => { setExecutionMode(value); resetMessages() }}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('strategy.selectExecutionMode', 'Select execution mode')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="real">{t('strategy.executionReal', 'Live Trading')}</SelectItem>
                      <SelectItem value="paper">{t('strategy.executionPaper', 'Paper Trading')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {executionMode === 'paper'
                      ? t('strategy.executionPaperHint', 'Simulated fills on live mainnet data. No wallet required.')
                      : t('strategy.executionRealHint', 'Orders are sent to the real exchange.')}
                  </p>
                </div>

                <section className="space-y-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.signalPools', 'Signal Pools')}</div>
                  <div className="border rounded-md p-3 space-y-2 max-h-48 overflow-y-auto">
                    {signalPools.length === 0 ? (
                      <p className="text-sm text-muted-foreground">{t('strategy.noSignalPoolsAvailable', 'No signal pools available. Create one in the Signals tab.')}</p>
                    ) : (
                      signalPools.map((pool) => {
                        const isSelected = signalPoolIds.includes(pool.id)
                        return (
                          <label key={pool.id} className="flex items-center gap-2 cursor-pointer hover:bg-muted/50 p-1 rounded">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {
                                setSignalPoolIds(prev =>
                                  isSelected
                                    ? prev.filter(id => id !== pool.id)
                                    : [...prev, pool.id]
                                )
                                resetMessages()
                              }}
                              className="h-4 w-4"
                            />
                            <span className="text-sm">{pool.pool_name}</span>
                            <span className="text-xs text-muted-foreground">({pool.logic || 'OR'})</span>
                          </label>
                        )
                      })
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {signalPoolIds.length > 0
                      ? t('strategy.triggerWhenAnyMet', 'Trigger when ANY selected pool conditions are met (OR relationship)')
                      : t('strategy.scheduledOnly', 'Only use scheduled interval trigger')}
                  </p>
                  {signalPoolIds.length > 1 && (
                    <p className="text-xs text-yellow-600 dark:text-yellow-400">
                      {t('strategy.multiPoolWarning', 'Note: If multiple pools trigger simultaneously, only the first will execute (others are ignored while running).')}
                    </p>
                  )}
                </section>

                <section className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.triggerInterval', 'Trigger Interval (seconds)')}</div>
                    <Switch
                      checked={scheduledTriggerEnabled}
                      onCheckedChange={(checked) => {
                        setScheduledTriggerEnabled(checked)
                        resetMessages()
                      }}
                    />
                  </div>
                  <Input
                    type="number"
                    min={30}
                    step={30}
                    value={triggerInterval}
                    disabled={!scheduledTriggerEnabled}
                    onChange={(event) => {
                      setTriggerInterval(event.target.value)
                      resetMessages()
                    }}
                    className={!scheduledTriggerEnabled ? 'opacity-50' : ''}
                  />
                  <p className="text-xs text-muted-foreground">
                    {scheduledTriggerEnabled
                      ? t('strategy.triggerIntervalHint', 'Maximum time between triggers (default: 150s)')
                      : t('strategy.scheduledTriggerDisabled', 'Scheduled trigger is disabled. AI will only run on signal pool triggers.')}
                  </p>
                </section>

                {/* Warning when no trigger method is active */}
                {!scheduledTriggerEnabled && signalPoolIds.length === 0 && (
                  <div className="rounded-md bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 p-3">
                    <p className="text-sm text-yellow-800 dark:text-yellow-200">
                      {t('strategy.noTriggerWarning', 'Warning: This AI Trader has no active trigger method. It will not execute any trades until you enable scheduled trigger or bind a signal pool.')}
                    </p>
                  </div>
                )}

                <section className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.strategyStatus', 'Strategy Status')}</div>
                      <p className="text-xs text-muted-foreground">{enabled ? t('strategy.enabledDesc', 'Enabled: strategy reacts to signals and scheduled triggers.') : t('strategy.disabledDesc', 'Disabled: strategy will not auto-trade.')}</p>
                      {!autoTradingEnabled && (
                        <p className="text-xs text-muted-foreground">{t('strategy.accountAutoTradingPaused', 'Account auto-trading is paused')}</p>
                      )}
                    </div>
                    <Switch
                      checked={enabled}
                      onCheckedChange={(checked) => {
                        setEnabled(checked)
                        resetMessages()
                      }}
                    />
                  </div>
                </section>

                <section className="space-y-1 text-sm">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.lastTrigger', 'Last Trigger')}</div>
                  <div className="text-xs">{formatTimestamp(lastTriggerAt)}</div>
                </section>

                <Button onClick={handleSaveTrader} disabled={saving} className="w-full">
                  {saving ? t('strategy.saving', 'Saving…') : t('strategy.saveTraderConfig', 'Save Trader Config')}
                </Button>
              </CardContent>
            </Card>

              </>
            )}
          </TabsContent>
          <TabsContent value="watchlist" className="flex-1 overflow-y-auto space-y-4">
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <div className="text-muted-foreground mb-4">
                {t('strategy.watchlistMoved', 'Watchlist management has been moved to Settings.')}
              </div>
              <div className="text-sm text-muted-foreground mb-4">
                {t('strategy.currentWatchlist', 'Current watchlist')}: {watchlistSymbols.join(', ') || '—'}
              </div>
              <Button
                variant="outline"
                onClick={() => {
                  window.location.hash = 'settings'
                  window.location.reload()
                }}
              >
                {t('strategy.goToSettings', 'Go to Settings')}
              </Button>
            </div>
          </TabsContent>
          <TabsContent value="global" className="flex-1 overflow-y-auto space-y-4">
            {loading ? (
              <div className="text-sm text-muted-foreground">{t('strategy.loadingConfig', 'Loading configuration…')}</div>
            ) : (
              <Card className="border-muted">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">{t('strategy.globalConfig', 'Global Configuration')}</CardTitle>
                  <CardDescription className="text-xs">{t('strategy.globalDesc', 'Settings that affect all traders')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <section className="space-y-2">
                    <div className="text-xs text-muted-foreground uppercase tracking-wide">{t('strategy.samplingInterval', 'Sampling Interval (seconds)')}</div>
                    <Input
                      type="number"
                      min={5}
                      max={60}
                      step={1}
                      value={samplingInterval}
                      onChange={(event) => {
                        setSamplingInterval(event.target.value)
                        resetMessages()
                      }}
                    />
                    <p className="text-xs text-muted-foreground">{t('strategy.samplingHint', 'How often to collect price samples (default: 18s)')}</p>
                  </section>

                  {error && <div className="text-sm text-destructive">{error}</div>}
                  {success && <div className="text-sm text-green-500">{success}</div>}

                  <Button onClick={handleSaveGlobal} disabled={saving} className="w-full">
                    {saving ? t('strategy.saving', 'Saving…') : t('strategy.saveGlobalSettings', 'Save Global Settings')}
                  </Button>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
    </div>
  )
}
