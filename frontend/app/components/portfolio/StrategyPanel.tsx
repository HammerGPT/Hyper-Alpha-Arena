import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

interface StrategyConfig {
  price_threshold: number
  interval_seconds: number
  enabled: boolean
  last_trigger_at?: string | null
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

function formatTimestamp(value?: string | null): string {
  if (!value) return 'No executions yet'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString([], {
    hour12: false,
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export default function StrategyPanel({
  accountId,
  accountName,
  refreshKey,
  accounts,
  onAccountChange,
  accountsLoading = false,
}: StrategyPanelProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Trader-specific settings
  const [priceThreshold, setPriceThreshold] = useState<string>('1.0')
  const [triggerInterval, setTriggerInterval] = useState<string>('150')
  const [enabled, setEnabled] = useState<boolean>(true)
  const [lastTriggerAt, setLastTriggerAt] = useState<string | null>(null)

  // Global settings
  const [samplingInterval, setSamplingInterval] = useState<string>('18')

  const resetMessages = useCallback(() => {
    setError(null)
    setSuccess(null)
  }, [])

  const fetchStrategy = useCallback(async () => {
    setLoading(true)
    resetMessages()
    try {
      // Fetch trader-specific config
      const strategyResponse = await fetch(`/api/account/${accountId}/strategy`)
      if (strategyResponse.ok) {
        const strategy: StrategyConfig = await strategyResponse.json()
        setPriceThreshold((strategy.price_threshold ?? 1.0).toString())
        setTriggerInterval((strategy.interval_seconds ?? 150).toString())
        setEnabled(strategy.enabled)
        setLastTriggerAt(strategy.last_trigger_at ?? null)
      }

      // Fetch global sampling config
      const globalResponse = await fetch('/api/config/global-sampling')
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

  useEffect(() => {
    fetchStrategy()
  }, [fetchStrategy, refreshKey])

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

  useEffect(() => {
    resetMessages()
  }, [accountId, resetMessages])

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
        trigger_mode: "unified",
        tick_batch_size: 1
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
      setLastTriggerAt(result.last_trigger_at ?? null)

      setSuccess('Trader configuration saved successfully.')
    } catch (err) {
      console.error('Failed to update trader config', err)
      setError(err instanceof Error ? err.message : 'Failed to save trader configuration.')
    } finally {
      setSaving(false)
    }
  }, [accountId, priceThreshold, triggerInterval, enabled, resetMessages])

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
    <Card className="h-full flex flex-col">
      <CardHeader>
        <CardTitle>AI Strategy Settings</CardTitle>
        <CardDescription>Configure trigger parameters for AI traders</CardDescription>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto space-y-6">
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading strategy…</div>
        ) : (
          <>
            {/* Trader Selection */}
            <section className="space-y-2">
              <div className="text-xs text-muted-foreground uppercase tracking-wide">Select Trader</div>
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
                    <SelectValue placeholder={accountsLoading ? 'Loading traders…' : 'Select AI trader'} />
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
                    <CardTitle className="text-base">Trader Configuration</CardTitle>
                    <CardDescription className="text-xs">Settings for {selectedAccountLabel}</CardDescription>
                  </div>
                  <div className="flex flex-col space-y-1">
                    {error && <div className="text-sm text-destructive">{error}</div>}
                    {success && <div className="text-sm text-green-500">{success}</div>}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <section className="space-y-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Price Threshold (%)</div>
                  <Input
                    type="number"
                    min={0.1}
                    max={10.0}
                    step={0.1}
                    value={priceThreshold}
                    onChange={(event) => {
                      setPriceThreshold(event.target.value)
                      resetMessages()
                    }}
                  />
                  <p className="text-xs text-muted-foreground">Trigger when price changes by this percentage</p>
                </section>

                <section className="space-y-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Trigger Interval (seconds)</div>
                  <Input
                    type="number"
                    min={30}
                    step={30}
                    value={triggerInterval}
                    onChange={(event) => {
                      setTriggerInterval(event.target.value)
                      resetMessages()
                    }}
                  />
                  <p className="text-xs text-muted-foreground">Maximum time between triggers (default: 150s)</p>
                </section>

                <section className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-muted-foreground uppercase tracking-wide">Strategy Status</div>
                      <p className="text-xs text-muted-foreground">{enabled ? 'Enabled: strategy reacts to price events.' : 'Disabled: strategy will not auto-trade.'}</p>
                    </div>
                    <label className="inline-flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(event) => {
                          setEnabled(event.target.checked)
                          resetMessages()
                        }}
                        className="h-4 w-4"
                      />
                      {enabled ? 'Enabled' : 'Disabled'}
                    </label>
                  </div>
                </section>

                <section className="space-y-1 text-sm">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Last Trigger</div>
                  <div className="text-xs">{formatTimestamp(lastTriggerAt)}</div>
                </section>

                <Button onClick={handleSaveTrader} disabled={saving} className="w-full">
                  {saving ? 'Saving…' : 'Save Trader Config'}
                </Button>
              </CardContent>
            </Card>

            {/* Global Configuration */}
            <Card className="border-muted">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Global Configuration</CardTitle>
                <CardDescription className="text-xs">Settings that affect all traders</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <section className="space-y-2">
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Sampling Interval (seconds)</div>
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
                  <p className="text-xs text-muted-foreground">How often to collect price samples (default: 18s)</p>
                </section>

                <Button onClick={handleSaveGlobal} disabled={saving} className="w-full">
                  {saving ? 'Saving…' : 'Save Global Settings'}
                </Button>
              </CardContent>
            </Card>

                      </>
        )}
      </CardContent>
    </Card>
  )
}