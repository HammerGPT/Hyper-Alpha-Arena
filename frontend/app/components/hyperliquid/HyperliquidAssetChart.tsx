/**
 * HyperliquidAssetChart - Multi-Account Asset Curve Chart for Hyperliquid Mode
 *
 * Used by: HyperliquidView (line 6 import, line 56 usage)
 *
 * Features:
 * - 5-minute bucketed asset snapshots
 * - Multi-account display with individual curves
 * - Baseline reference line for profit/loss visualization
 * - Terminal dots with account logos and current values
 *
 * Data source: /api/account/asset-curve with environment parameter (testnet/mainnet)
 * Backend field: total_assets (NOT total_equity - field name fixed in v0.5.1)
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  LineChart,
  Line,
  Area,
  AreaChart,
  ComposedChart,
  ReferenceLine,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts'
import { Card } from '@/components/ui/card'
import { getModelChartLogo, getModelColor } from '../portfolio/logoAssets'
import FlipNumber from '../portfolio/FlipNumber'
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid'

interface HyperliquidAssetData {
  timestamp: number
  datetime_str: string
  account_id: number
  total_assets: number
  username: string
  wallet_address?: string | null
}

interface HyperliquidAssetChartProps {
  accountId: number
  refreshTrigger?: number
  environment?: HyperliquidEnvironment
  selectedAccount?: number | 'all'
}

export default function HyperliquidAssetChart({
  accountId,
  refreshTrigger,
  environment,
  selectedAccount,
}: HyperliquidAssetChartProps) {
  const [data, setData] = useState<HyperliquidAssetData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [logoPulseMap, setLogoPulseMap] = useState<Map<number, number>>(new Map())

  // Fetch Hyperliquid asset curve data (5-minute bucketed)
  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const params = new URLSearchParams({
        timeframe: '5m',
        trading_mode: environment || 'testnet',
      })
      if (environment) {
        params.set('environment', environment)
      }
      if (selectedAccount && selectedAccount !== 'all') {
        params.set('account_id', String(selectedAccount))
      }

      const response = await fetch(`/api/account/asset-curve?${params.toString()}`)
      if (!response.ok) {
        throw new Error('Failed to fetch asset curve data')
      }

      const assetData = await response.json()
      setData(assetData || [])
    } catch (err) {
      console.error('Error fetching Hyperliquid asset curve:', err)
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [environment, selectedAccount])

  useEffect(() => {
    fetchData()
  }, [fetchData, refreshTrigger])

  // Process chart data
  const { chartData, accountsData, yAxisDomain, baseline } = useMemo(() => {
    if (!data.length) return { chartData: [], accountsData: [], yAxisDomain: [0, 1000], baseline: 1000 }

    // Group by timestamp and create chart points
    const timeGroups = new Map<number, any>()
    const accounts = new Map<number, { username: string; logo: { src: string; alt: string; color?: string } }>()

    data.forEach(item => {
      if (!timeGroups.has(item.timestamp)) {
        timeGroups.set(item.timestamp, {
          timestamp: item.timestamp,
          datetime_str: item.datetime_str
        })
      }

      const point = timeGroups.get(item.timestamp)!
      point[item.username] = item.total_assets

      accounts.set(item.account_id, {
        username: item.username,
        logo: getModelChartLogo(item.username)
      })
    })

    const chartData = Array.from(timeGroups.values()).sort((a, b) => a.timestamp - b.timestamp)
    const accountsData = Array.from(accounts.entries()).map(([id, info]) => ({
      account_id: id,
      ...info
    }))

    // Calculate baseline (initial capital)
    const baseline = chartData.length > 0 && accountsData.length > 0 ?
      chartData[0][accountsData[0].username] || 1000 : 1000

    // Calculate Y-axis domain with smart padding
    const allValues = data.map(item => item.total_assets).filter(val => typeof val === 'number')

    if (allValues.length === 0) return { chartData, accountsData, yAxisDomain: [0, 1000], baseline }

    const minValue = Math.min(...allValues)
    const maxValue = Math.max(...allValues)
    const range = maxValue - minValue

    const hasMultipleAccounts = accountsData.length > 1
    const paddingPercent = hasMultipleAccounts ? 0.05 : 0.15
    const padding = range * paddingPercent

    return {
      chartData,
      accountsData,
      yAxisDomain: [Math.max(0, minValue - padding), maxValue + padding],
      baseline
    }
  }, [data])

  // Terminal dot renderer with logo and value
  const renderTerminalDot = useCallback(
    (account: { account_id: number; username: string; logo: { src: string; alt: string; color?: string } }) =>
      (props: { cx?: number; cy?: number; index?: number; value?: number; payload?: any }) => {
        const { cx, cy, index, payload } = props
        if (cx == null || cy == null || index == null || !payload) return null
        if (chartData.length === 0 || index !== chartData.length - 1) return null

        const value = payload[account.username]
        if (typeof value !== 'number') return null

        const color = account.logo?.color || getModelColor(account.username)
        const pulseIteration = logoPulseMap.get(account.account_id) ?? 0
        const size = 32
        const logoX = cx - size / 2
        const logoY = cy - size / 2
        const labelX = cx + size / 2 + 2
        const labelY = cy - 18

        return (
          <g>
            {pulseIteration > 0 && (
              <circle
                cx={cx}
                cy={cy}
                r={size / 2}
                fill={color}
                className="pointer-events-none animate-ping-logo"
              />
            )}
            <foreignObject
              x={logoX}
              y={logoY}
              width={size}
              height={size}
              style={{ overflow: 'visible', pointerEvents: 'none' }}
            >
              <div
                style={{
                  width: size,
                  height: size,
                  borderRadius: '50%',
                  backgroundColor: color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 2px 6px rgba(0,0,0,0.16)',
                }}
              >
                <img
                  src={account.logo?.src}
                  alt={account.logo?.alt}
                  style={{
                    width: size - 6,
                    height: size - 6,
                    borderRadius: '50%',
                    objectFit: 'contain',
                  }}
                />
              </div>
            </foreignObject>

            <foreignObject
              x={labelX}
              y={labelY}
              width={120}
              height={24}
              style={{ overflow: 'visible', pointerEvents: 'none' }}
            >
              <div
                className="px-3 py-1 text-xs font-semibold text-white"
                style={{
                  borderRadius: '12px',
                  backgroundColor: color,
                  display: 'inline-block',
                  boxShadow: '0 4px 10px rgba(0,0,0,0.18)',
                }}
              >
                <FlipNumber value={value} prefix="$" decimals={2} className="text-white" />
              </div>
            </foreignObject>
          </g>
        )
      },
    [chartData, logoPulseMap]
  )

  if (loading && data.length === 0) {
    return (
      <Card className="h-full flex items-center justify-center">
        <div className="text-muted-foreground">Loading Hyperliquid data...</div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="h-full flex items-center justify-center">
        <div className="text-destructive">{error}</div>
      </Card>
    )
  }

  if (chartData.length === 0) {
    return (
      <Card className="h-full flex items-center justify-center">
        <div className="text-muted-foreground">
          No Hyperliquid snapshot data yet.
        </div>
      </Card>
    )
  }

  return (
    <Card className="h-full">
      <div className="h-full relative">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 20, right: 160, left: 20, bottom: 40 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="datetime_str"
              stroke="#888"
              fontSize={11}
              interval={Math.ceil(chartData.length / 6)}
              tickFormatter={(value) => {
                if (!value) return ''
                const [datePart, timePart] = value.split(' ')
                return `${datePart}\n${timePart}`
              }}
            />
            <YAxis
              stroke="#888"
              fontSize={11}
              domain={yAxisDomain}
              tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(255,255,255,0.95)',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
              }}
              formatter={(value: number, name: string) => [
                `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                name
              ]}
            />

            <ReferenceLine y={baseline} stroke="#9CA3AF" strokeDasharray="4 4" ifOverflow="extendDomain" />

            {accountsData.length === 1 && (
              <Area
                type="monotone"
                dataKey={accountsData[0].username}
                stroke="none"
                fill="rgba(34,197,94,0.08)"
                baseValue={baseline}
                isAnimationActive={false}
              />
            )}

            {accountsData.map(account => {
              const color = account.logo?.color || getModelColor(account.username)
              return (
                <Line
                  key={account.account_id}
                  type="monotone"
                  dataKey={account.username}
                  stroke={color}
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 6, fill: color }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              )
            })}

            {/* Terminal dots with logos */}
            {accountsData.map(account => (
              <Line
                key={`terminal-${account.account_id}`}
                type="monotone"
                dataKey={account.username}
                stroke="transparent"
                strokeWidth={0}
                dot={renderTerminalDot(account)}
                activeDot={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
