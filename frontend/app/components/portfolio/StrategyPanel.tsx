import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { StrategyConfig, StrategyConfigUpdate, StrategyTriggerMode, getAccountStrategy, updateAccountStrategy } from '@/lib/api'

interface StrategyPanelProps {
  accountId: number
  accountName: string
  refreshKey?: number
  accounts?: Array<{ id: number; name: string; model?: string | null }>
  onAccountChange?: (accountId: number) => void
  accountsLoading?: boolean
}

const MODE_OPTIONS: Array<{ value: StrategyTriggerMode; label: string; helper: string }> = [
  { value: 'realtime', label: 'Real-time Trigger', helper: 'Execute on every market update.' },
  { value: 'interval', label: 'Fixed Interval', helper: 'Execute decisions on a timed interval.' },
  { value: 'tick_batch', label: 'Tick Batch', helper: 'Execute after a set number of price updates.' },
]

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

  const [triggerMode, setTriggerMode] = useState<StrategyTriggerMode>('realtime')
  const [intervalSeconds, setIntervalSeconds] = useState<string>('60')
  const [tickBatchSize, setTickBatchSize] = useState<string>('3')
  const [enabled, setEnabled] = useState<boolean>(true)
  const [lastTriggerAt, setLastTriggerAt] = useState<string | null>(null)

  const resetMessages = useCallback(() => {
    setError(null)
    setSuccess(null)
  }, [])

  const applyStrategy = useCallback((strategy: StrategyConfig) => {
    setTriggerMode(strategy.trigger_mode)
    setIntervalSeconds(strategy.interval_seconds?.toString() ?? '60')
    setTickBatchSize(strategy.tick_batch_size?.toString() ?? '3')
    setEnabled(strategy.enabled)
    setLastTriggerAt(strategy.last_trigger_at ?? null)
  }, [])

  const fetchStrategy = useCallback(async () => {
    setLoading(true)
    resetMessages()
    try {
      const strategy = await getAccountStrategy(accountId)
      applyStrategy(strategy)
    } catch (err) {
      console.error('Failed to load strategy config', err)
      if (err instanceof Error && /50[02]/.test(err.message)) {
        setError('Strategy service unavailable. Please ensure the backend is running and try again shortly.')
      } else {
        setError(err instanceof Error ? err.message : 'Unable to load strategy configuration.')
      }
    } finally {
      setLoading(false)
    }
  }, [accountId, applyStrategy, resetMessages])

  useEffect(() => {
    fetchStrategy()
  }, [fetchStrategy, refreshKey])

  const modeDetails = useMemo(() => MODE_OPTIONS.find((option) => option.value === triggerMode), [triggerMode])

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

  const buildPayload = useCallback((): StrategyConfigUpdate | null => {
    if (triggerMode === 'interval') {
      const value = Number(intervalSeconds)
      if (!Number.isFinite(value) || value <= 0) {
        setError('Interval must be a positive number of seconds.')
        return null
      }
      return {
        trigger_mode: triggerMode,
        interval_seconds: Math.round(value),
        enabled,
      }
    }

    if (triggerMode === 'tick_batch') {
      const value = Number(tickBatchSize)
      if (!Number.isInteger(value) || value <= 0) {
        setError('Batch size must be a positive integer.')
        return null
      }
      return {
        trigger_mode: triggerMode,
        tick_batch_size: value,
        enabled,
      }
    }

    return {
      trigger_mode: triggerMode,
      enabled,
    }
  }, [triggerMode, intervalSeconds, tickBatchSize, enabled])

  const handleSave = useCallback(async () => {
    resetMessages()
    const payload = buildPayload()
    if (!payload) return

    try {
      setSaving(true)
      const result = await updateAccountStrategy(accountId, payload)
      applyStrategy(result)
      setSuccess('Strategy saved. It will take effect on the next market update.')
    } catch (err) {
      console.error('Failed to update strategy config', err)
      if (err instanceof Error && /50[02]/.test(err.message)) {
        setError('Save failed: strategy service unavailable. Please confirm the backend has been restarted.')
      } else {
        setError(err instanceof Error ? err.message : 'Failed to save strategy. Please retry shortly.')
      }
    } finally {
      setSaving(false)
    }
  }, [accountId, applyStrategy, buildPayload, resetMessages])

  return (
    <Card className="h-full flex flex-col">
      <CardHeader>
        <CardTitle>AI Strategy Settings</CardTitle>
        <CardDescription>Trigger configuration for {selectedAccountLabel}</CardDescription>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto space-y-5">
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading strategy…</div>
        ) : (
          <>
            <section className="space-y-2">
              <div className="text-xs text-muted-foreground uppercase tracking-wide">AI Trader</div>
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

            <section className="space-y-2">
              <div className="text-xs text-muted-foreground uppercase tracking-wide">Trigger Mode</div>
              <Select value={triggerMode} onValueChange={(value) => { setTriggerMode(value as StrategyTriggerMode); resetMessages() }}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select trigger mode" />
                </SelectTrigger>
                <SelectContent>
                  {MODE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {modeDetails && (
                <p className="text-xs text-muted-foreground leading-relaxed">{modeDetails.helper}</p>
              )}
            </section>

            {triggerMode === 'interval' && (
              <section className="space-y-2">
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Interval (seconds)</div>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={intervalSeconds}
                  onChange={(event) => {
                    setIntervalSeconds(event.target.value)
                    resetMessages()
                  }}
                />
              </section>
            )}

            {triggerMode === 'tick_batch' && (
              <section className="space-y-2">
                <div className="text-xs text-muted-foreground uppercase tracking-wide">Batch Size (updates)</div>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={tickBatchSize}
                  onChange={(event) => {
                    setTickBatchSize(event.target.value)
                    resetMessages()
                  }}
                />
                <p className="text-xs text-muted-foreground">Execute once this many price updates occur, then reset the counter.</p>
              </section>
            )}

            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs text-muted-foreground uppercase tracking-wide">Strategy Status</div>
                  <p className="text-sm text-muted-foreground">{enabled ? 'Enabled: strategy reacts to price events.' : 'Disabled: strategy will not auto-trade.'}</p>
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
              <div>{formatTimestamp(lastTriggerAt)}</div>
            </section>

            {error && <div className="text-sm text-destructive">{error}</div>}
            {success && <div className="text-sm text-green-500">{success}</div>}

            <div className="pt-2">
              <Button onClick={handleSave} disabled={saving} className="w-full">
                {saving ? 'Saving…' : 'Save Strategy'}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
