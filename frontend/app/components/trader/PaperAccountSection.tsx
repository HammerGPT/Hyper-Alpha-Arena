import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { RefreshCw, RotateCcw } from 'lucide-react'

interface PaperState {
  configured: boolean
  account_id: number
  data_exchange?: string
  cycle?: number
  initial_capital?: number
  total_equity?: number
  available_balance?: number
  unrealized_pnl?: number
  cycle_return_pct?: number
  positions?: any[]
}

export default function PaperAccountSection({ accountId }: { accountId: number }) {
  const { t } = useTranslation()
  const [state, setState] = useState<PaperState | null>(null)
  const [loading, setLoading] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [initialCapital, setInitialCapital] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch(`/api/paper-trading/${accountId}/state`)
      if (resp.ok) {
        const data = await resp.json()
        setState(data)
        if (data.initial_capital) setInitialCapital(String(data.initial_capital))
      }
    } catch (e) {
      console.error('Failed to load paper state:', e)
    } finally {
      setLoading(false)
    }
  }, [accountId])

  useEffect(() => { load() }, [load])

  const handleReset = async () => {
    const confirmed = window.confirm(
      t('paper.resetConfirm',
        'Reset paper account? Positions and pending orders are cleared, equity returns to initial capital, and a new cycle starts. History is preserved.')
    )
    if (!confirmed) return
    setResetting(true)
    try {
      const capital = parseFloat(initialCapital)
      const resp = await fetch(`/api/paper-trading/${accountId}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Number.isFinite(capital) && capital > 0 ? { initial_capital: capital } : {}),
      })
      if (resp.ok) setState(await resp.json())
    } catch (e) {
      console.error('Failed to reset paper account:', e)
    } finally {
      setResetting(false)
    }
  }

  if (!state?.configured) {
    return (
      <div className="border rounded-lg p-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="secondary" className="text-[10px]">PAPER</Badge>
          <span className="font-medium text-foreground">{t('paper.title', 'Paper Trading Account')}</span>
        </div>
        {t('paper.notConfigured', 'Enable Paper Trading in the strategy config. The account is created on first trade.')}
      </div>
    )
  }

  const pnlColor = (state.cycle_return_pct ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'

  return (
    <div className="border rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="text-[10px]">PAPER</Badge>
          <span className="text-sm font-medium">{t('paper.title', 'Paper Trading Account')}</span>
          <span className="text-xs text-muted-foreground">
            {t('paper.cycle', 'Cycle')} #{state.cycle} · {state.data_exchange}
          </span>
        </div>
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={load} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">{t('paper.equity', 'Equity')}</div>
          <div className="font-mono font-medium">${state.total_equity?.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t('paper.available', 'Available')}</div>
          <div className="font-mono">${state.available_balance?.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted-foreground">{t('paper.cycleReturn', 'Cycle Return')}</div>
          <div className={`font-mono font-medium ${pnlColor}`}>
            {(state.cycle_return_pct ?? 0) >= 0 ? '+' : ''}{state.cycle_return_pct}%
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <input
          type="number"
          value={initialCapital}
          onChange={(e) => setInitialCapital(e.target.value)}
          className="w-28 border border-border rounded px-2 py-1 text-xs bg-background"
          placeholder="10000"
        />
        <span className="text-xs text-muted-foreground">{t('paper.initialCapital', 'Initial capital (USD)')}</span>
        <Button variant="outline" size="sm" className="h-7 ml-auto text-xs" onClick={handleReset} disabled={resetting}>
          <RotateCcw className="h-3 w-3 mr-1" />
          {t('paper.reset', 'Reset')}
        </Button>
      </div>
    </div>
  )
}
