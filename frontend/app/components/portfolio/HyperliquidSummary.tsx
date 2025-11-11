import { useEffect, useState } from 'react'
import { Card } from '@/components/ui/card'
import BalanceCard from '@/components/hyperliquid/BalanceCard'
import { getHyperliquidConfig } from '@/lib/hyperliquidApi'
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid'
import { useTradingMode } from '@/contexts/TradingModeContext'

interface HyperliquidSummaryProps {
  accountId?: number | null
  refreshKey?: number
}

type SummaryState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; environment: HyperliquidEnvironment }
  | { status: 'disabled'; message: string }
  | { status: 'error'; message: string }

export default function HyperliquidSummary({ accountId, refreshKey }: HyperliquidSummaryProps) {
  const { tradingMode } = useTradingMode()
  const [state, setState] = useState<SummaryState>({ status: 'idle' })

  useEffect(() => {
    if (tradingMode === 'paper') {
      setState({ status: 'idle' })
      return
    }
    if (!accountId) {
      setState({
        status: 'disabled',
        message: 'No Hyperliquid account detected. Please configure it in Trader Management first.',
      })
      return
    }

    let cancelled = false
    const loadConfig = async () => {
      setState({ status: 'loading' })
      try {
        const config = await getHyperliquidConfig(accountId)
        if (cancelled) return

        const enabled = Boolean((config as any).hyperliquid_enabled ?? config.enabled)
        if (!enabled) {
          setState({
            status: 'disabled',
            message: 'Hyperliquid is disabled. Please finish the setup on the Hyperliquid Trading page.',
          })
          return
        }

        const keyFlag =
          tradingMode === 'testnet'
            ? (config as any).hasTestnetKey
            : tradingMode === 'mainnet'
              ? (config as any).hasMainnetKey
              : true

        if (keyFlag === false) {
          const envLabel = tradingMode === 'testnet' ? 'Testnet' : 'Mainnet'
          setState({
            status: 'disabled',
            message: `Missing ${envLabel} API credentials. Please add them on the Hyperliquid Trading page.`,
          })
          return
        }

        setState({
          status: 'ready',
          environment:
            (config.environment as HyperliquidEnvironment | undefined) ??
            (tradingMode as HyperliquidEnvironment),
        })
      } catch (error: any) {
        if (cancelled) return
        const detail =
          error?.message || 'Failed to load Hyperliquid configuration. Please try again later.'
        setState({ status: 'error', message: detail })
      }
    }

    loadConfig()
    return () => {
      cancelled = true
    }
  }, [accountId, tradingMode])

  if (tradingMode === 'paper') {
    return null
  }

  if (state.status === 'idle') {
    return null
  }

  if (state.status === 'loading') {
    return (
      <Card className="border text-card-foreground shadow p-6 flex items-center justify-center">
        <div className="text-sm text-muted-foreground">Loading Hyperliquid data...</div>
      </Card>
    )
  }

  if (state.status === 'disabled') {
    return (
      <Card className="border text-card-foreground shadow p-6 space-y-3">
        <div className="text-sm text-muted-foreground leading-relaxed">
          {state.message}
        </div>
      </Card>
    )
  }

  if (state.status === 'error') {
    return (
      <Card className="border text-card-foreground shadow p-6 space-y-3">
        <div className="text-sm text-muted-foreground leading-relaxed">
          {state.message}
        </div>
      </Card>
    )
  }

  return (
    <BalanceCard
      accountId={accountId!}
      environment={state.environment}
      autoRefresh={false}
      refreshInterval={30}
      refreshToken={refreshKey}
    />
  )
}
