import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts'
import { Card } from '@/components/ui/card'
import { getModelChartLogo } from './logoAssets'
import FlipNumber from './FlipNumber'

interface AssetCurveData {
  timestamp?: number
  datetime_str?: string
  date?: string
  account_id: number
  total_assets: number
  cash: number
  positions_value: number
  is_initial?: boolean
  user_id: number
  username: string
}

interface AssetCurveProps {
  data?: AssetCurveData[]
  wsRef?: React.MutableRefObject<WebSocket | null>
  highlightAccountId?: number | 'all'
  onHighlightAccountChange?: (accountId: number | 'all') => void
}

type Timeframe = '5m' | '1h' | '1d' | 'all'
const DEFAULT_TIMEFRAME: Timeframe = '5m'
const CACHE_STALE_MS = 45_000

type DisplayMode = 'absolute' | 'percentage'

interface TimeframeCacheEntry {
  data: AssetCurveData[]
  lastFetched: number
  initialized: boolean
}

export default function AssetCurve({
  data: initialData,
  wsRef,
  highlightAccountId,
  onHighlightAccountChange
}: AssetCurveProps) {
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME)
  const [displayMode, setDisplayMode] = useState<DisplayMode>('absolute')
  const [hiddenAccounts, setHiddenAccounts] = useState<Set<number>>(new Set())
  const [data, setData] = useState<AssetCurveData[]>(initialData || [])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const cacheRef = useState(new Map<Timeframe, TimeframeCacheEntry>())[0]
  const [liveAccountTotals, setLiveAccountTotals] = useState<Map<number, number>>(new Map())
  const [logoPulseMap, setLogoPulseMap] = useState<Map<number, number>>(new Map())
  const [hoveredAccountId, setHoveredAccountId] = useState<number | null>(null)

  const storeCache = useCallback((tf: Timeframe, nextData: AssetCurveData[]) => {
    cacheRef.set(tf, {
      data: nextData,
      lastFetched: Date.now(),
      initialized: true,
    })
  }, [cacheRef])

  const primeFromCache = useCallback((tf: Timeframe) => {
    const cached = cacheRef.get(tf)
    if (!cached) return false
    setData(cached.data)
    setLoading(false)
    setError(null)
    setIsInitialized(prev => prev || cached.initialized)
    return true
  }, [cacheRef])

  // Listen for WebSocket asset curve updates
  useEffect(() => {
    if (!wsRef?.current) return

    const handleMessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg?.type === 'arena_asset_update' && msg.accounts) {
          const accountsToPulse: number[] = []
          setLiveAccountTotals((prev) => {
            const next = new Map(prev)
            ;(msg.accounts as Array<{ account_id: number; total_assets?: number }>).forEach(
              (account) => {
                if (account?.account_id == null) {
                  return
                }
                const nextValue = Number(account.total_assets ?? 0)
                const previousValue = prev.get(account.account_id)
                if (previousValue !== undefined && previousValue !== nextValue) {
                  accountsToPulse.push(account.account_id)
                }
                next.set(account.account_id, nextValue)
              },
            )
            return next
          })
          if (accountsToPulse.length) {
            setLogoPulseMap((prev) => {
              const updated = new Map(prev)
              accountsToPulse.forEach((accountId) => {
                const current = updated.get(accountId) ?? 0
                updated.set(accountId, current + 1)
              })
              return updated
            })
          }
        }
        if (msg.type === 'asset_curve_data' || msg.type === 'asset_curve_update') {
          const tf = (msg.timeframe as Timeframe) ?? timeframe
          const nextData = msg.data || []
          storeCache(tf, nextData)
          if (tf === timeframe) {
            setData(nextData)
            if (msg.type === 'asset_curve_data') {
              setLoading(false)
              setError(null)
            }
            setIsInitialized(true)
          }
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    }

    wsRef.current.addEventListener('message', handleMessage)

    return () => {
      wsRef.current?.removeEventListener('message', handleMessage)
    }
  }, [wsRef, timeframe, storeCache])

  // Request data when timeframe changes
  useEffect(() => {
    const cached = cacheRef.get(timeframe)
    const isFresh = cached ? Date.now() - cached.lastFetched < CACHE_STALE_MS : false
    const hadCache = primeFromCache(timeframe)

    if (isFresh) return

    if (wsRef?.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (!hadCache) setLoading(true)
      setError(null)
      wsRef.current.send(JSON.stringify({
        type: 'get_asset_curve',
        timeframe,
      }))
    } else if (!hadCache && initialData && !isInitialized) {
      setData(initialData)
      setIsInitialized(true)
      storeCache(timeframe, initialData)
    }
  }, [timeframe, wsRef, initialData, isInitialized, primeFromCache, storeCache, cacheRef])

  if (!data || data.length === 0) {
    return (
      <Card className="p-6">
        <div className="flex items-center justify-center h-96">
          <div className="text-muted-foreground">
            {loading ? 'Loading...' : error || 'No asset data available'}
          </div>
        </div>
      </Card>
    )
  }

  const colors = [
    '#f7931a', '#627eea', '#9945ff', '#f3ba2f', '#23292f', '#c2a633',
    '#000000', '#333333'
  ]

  // Split processedData into stable and live parts to reduce re-renders
  const baseProcessedData = useMemo(() => {
    if (!data || data.length === 0) {
      return { chartData: [], accountSummaries: [], uniqueUsers: [], userAccountMap: new Map() }
    }

    const uniqueUsers = Array.from(new Set(data.map(item => item.username))).sort()
    const userAccountMap = new Map<string, number | undefined>()

    const groupedData = data.reduce((acc, item) => {
      const key = item.datetime_str || item.date || item.timestamp?.toString() || ''
      if (!acc[key]) acc[key] = { timestamp: key }

      const accountId = item.account_id
      if (!userAccountMap.has(item.username)) {
        userAccountMap.set(item.username, accountId)
      }

      acc[key][item.username] = item.total_assets ?? null
      return acc
    }, {} as Record<string, any>)

    const parseTimestamp = (value: string) => {
      if (/^\d+$/.test(value)) {
        const numeric = Number(value)
        const milliseconds = value.length <= 10 ? numeric * 1000 : numeric
        return new Date(milliseconds)
      }
      return new Date(value)
    }

    const timestamps = Object.keys(groupedData).sort((a, b) => {
      const dateA = parseTimestamp(a).getTime()
      const dateB = parseTimestamp(b).getTime()
      return dateA - dateB
    })

    const chartData = timestamps.map((ts) => {
      const date = parseTimestamp(ts)
      const formattedTime = date.toLocaleString('en-US', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      })

      const dataPoint: Record<string, any> = {
        timestamp: ts,
        formattedTime,
      }
      
      uniqueUsers.forEach((username) => {
        dataPoint[username] = groupedData[ts][username] ?? null
      })

      return dataPoint
    })

    const accountSummaries = uniqueUsers.map((username) => {
      const latestData = data
        .filter((item) => item.username === username)
        .sort((a, b) => {
          const dateA = new Date(a.datetime_str || a.date || 0).getTime()
          const dateB = new Date(b.datetime_str || b.date || 0).getTime()
          return dateB - dateA
        })[0]

      return {
        username,
        assets: latestData?.total_assets || 0,
        accountId: latestData?.account_id,
        logo: getModelChartLogo(username),
      }
    })

    return { chartData, accountSummaries, uniqueUsers, userAccountMap }
  }, [data, timeframe])

  // Apply live updates to the last data point only
  const processedData = useMemo(() => {
    const { chartData, accountSummaries, uniqueUsers, userAccountMap } = baseProcessedData

    // Create a copy of chartData and update only the last point with live data
    const updatedChartData = [...chartData]
    if (updatedChartData.length > 0) {
      const lastPoint = { ...updatedChartData[updatedChartData.length - 1] }
      uniqueUsers.forEach((username) => {
        const accountId = userAccountMap.get(username)
        if (accountId !== undefined && accountId !== null) {
          const liveOverride = liveAccountTotals.get(accountId)
          if (liveOverride !== undefined) {
            lastPoint[username] = liveOverride
          }
        }
      })
      updatedChartData[updatedChartData.length - 1] = lastPoint
    }

    // Calculate initial values for percentage mode
    const initialValues = new Map<string, number>()
    if (displayMode === 'percentage' && updatedChartData.length > 0) {
      uniqueUsers.forEach(username => {
        const firstValue = updatedChartData[0][username]
        if (typeof firstValue === 'number' && firstValue > 0) {
          initialValues.set(username, firstValue)
        }
      })
    }

    // Convert to percentage if needed
    const displayChartData = displayMode === 'percentage' 
      ? updatedChartData.map(point => {
          const newPoint: any = { ...point }
          uniqueUsers.forEach(username => {
            const value = point[username]
            const initial = initialValues.get(username)
            if (typeof value === 'number' && initial && initial > 0) {
              newPoint[username] = ((value - initial) / initial) * 100
            } else if (typeof value === 'number' && initial) {
              newPoint[username] = 0
            }
          })
          return newPoint
        })
      : updatedChartData

    // Update account summaries with live data
    const updatedAccountSummaries = accountSummaries.map(account => {
      const liveOverride = account.accountId !== undefined ? liveAccountTotals.get(account.accountId) : undefined
      return {
        ...account,
        assets: liveOverride ?? account.assets
      }
    })

    const rankedAccounts = updatedAccountSummaries.slice().sort((a, b) => b.assets - a.assets)

    return {
      chartData: displayChartData,
      accountSummaries: updatedAccountSummaries,
      uniqueUsers,
      rankedAccounts,
      initialValues
    }
  }, [baseProcessedData, liveAccountTotals, displayMode])

  const { chartData, accountSummaries, uniqueUsers, rankedAccounts } = processedData

  const handleLegendClick = useCallback((accountId: number | 'all') => {
    if (!onHighlightAccountChange) return
    const current = highlightAccountId ?? 'all'
    if (current === accountId) {
      onHighlightAccountChange('all')
    } else {
      onHighlightAccountChange(accountId)
    }
  }, [onHighlightAccountChange, highlightAccountId])

  const toggleAccountVisibility = useCallback((accountId: number) => {
    setHiddenAccounts(prev => {
      const next = new Set(prev)
      if (next.has(accountId)) {
        next.delete(accountId)
      } else {
        next.add(accountId)
      }
      return next
    })
  }, [])

  const handleChartClick = useCallback(() => {
    if (highlightAccountId && highlightAccountId !== 'all') {
      onHighlightAccountChange?.('all')
    }
  }, [highlightAccountId, onHighlightAccountChange])

  const activeLegendAccountId =
    highlightAccountId && highlightAccountId !== 'all' ? highlightAccountId : null

  // Calculate Y-axis domain with single trader scaling
  const yAxisDomain = useMemo(() => {
    if (!chartData.length) {
      return displayMode === 'percentage' ? [-10, 10] : [0, 100000]
    }

    let min = Infinity
    let max = -Infinity

    // Filter users based on hidden accounts and legend selection
    const usersToConsider = uniqueUsers.filter(username => {
      const account = accountSummaries.find(acc => acc.username === username)
      if (!account?.accountId) return false
      if (hiddenAccounts.has(account.accountId)) return false
      if (activeLegendAccountId && account.accountId !== activeLegendAccountId) return false
      return true
    })

    chartData.forEach(point => {
      usersToConsider.forEach(username => {
        const value = point[username]
        if (typeof value === 'number' && !isNaN(value)) {
          min = Math.min(min, value)
          max = Math.max(max, value)
        }
      })
    })

    if (min === Infinity || max === -Infinity) {
      return displayMode === 'percentage' ? [-10, 10] : [0, 100000]
    }

    // Use different padding for single trader vs all traders view
    const range = max - min
    const paddingPercent = activeLegendAccountId ? 0.15 : 0.05 // 15% for single trader, 5% for all traders
    const padding = displayMode === 'percentage' 
      ? Math.max(range * paddingPercent, 1)
      : Math.max(range * paddingPercent, 50)

    const paddedMin = displayMode === 'percentage' 
      ? min - padding 
      : Math.max(0, min - padding)
    const paddedMax = max + padding

    return [paddedMin, paddedMax]
  }, [chartData, uniqueUsers, activeLegendAccountId, accountSummaries, highlightAccountId, hiddenAccounts, displayMode])

  const accountMeta = useMemo(() => {
    const meta = new Map<string, { accountId?: number; color: string; logo?: { src: string; alt: string; color?: string } }>()
    uniqueUsers.forEach((username, index) => {
      const account = accountSummaries.find(acc => acc.username === username)
      const chartLogo = getModelChartLogo(username)
      const color = chartLogo.color || colors[index % colors.length]
      meta.set(username, {
        accountId: account?.accountId,
        color,
        logo: account?.logo,
      })
    })
    return meta
  }, [uniqueUsers, accountSummaries])

  const renderTerminalDot = useCallback((username: string, color: string) => {
    const meta = accountMeta.get(username)
    const accountId = meta?.accountId
    const logo = meta?.logo

    return (props: { cx?: number; cy?: number; index?: number; value?: number }) => {
      const { cx, cy, index, value } = props
      if (cx == null || cy == null || index == null || index !== chartData.length - 1) {
        return <></>
      }
      if (!meta || !logo) return <></>

      // Single trader view: hide others completely
      if (activeLegendAccountId && accountId !== activeLegendAccountId) {
        return <></>
      }

      const isHovered = hoveredAccountId === accountId
      const shouldHighlight = !hoveredAccountId || isHovered
      const pulseIteration = accountId != null ? logoPulseMap.get(accountId) ?? 0 : 0

      const size = 32 // 固定大小，不再缩放
      const logoX = cx - size / 2
      const logoY = cy - size / 2
      const labelX = cx + size / 2 + 2
      const labelY = cy - 15

      const handleClick = (e: React.MouseEvent) => {
        e.stopPropagation()
        if (!meta.accountId) return
        handleLegendClick(meta.accountId)
      }

      const handleMouseEnter = () => {
        if (meta.accountId) setHoveredAccountId(meta.accountId)
      }

      const handleMouseLeave = () => {
        setHoveredAccountId(null)
      }

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
            style={{ overflow: 'visible', pointerEvents: 'auto' }}
          >
            <div
              style={{
                width: size,
                height: size,
                borderRadius: '50%',
                opacity: shouldHighlight ? 1 : 0.4,
                cursor: meta.accountId ? 'pointer' : 'default',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: color,
              }}
              onClick={handleClick}
              onMouseEnter={handleMouseEnter}
              onMouseLeave={handleMouseLeave}
            >
              <img
                src={logo.src}
                alt={logo.alt}
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
            height={18}
            style={{ overflow: 'visible', pointerEvents: 'none' }}
          >
            <div
              className="px-3 py-1 text-xs font-bold transition-opacity duration-150 ease-out"
              style={{
                backgroundColor: color,
                color: '#fff',
                boxShadow: '0 4px 8px rgba(0,0,0,0.12)',
                opacity: shouldHighlight ? 1 : 0.45,
                borderRadius: '12px',
                display: 'inline-block',
                whiteSpace: 'nowrap',
              }}
            >
              <FlipNumber
                value={typeof value === 'number' ? value : 0}
                prefix="$"
                decimals={2}
                className="text-white"
              />
            </div>
          </foreignObject>
        </g>
      )
    }
  }, [accountMeta, chartData.length, activeLegendAccountId, logoPulseMap, handleLegendClick, hoveredAccountId])


  return (
    <div className="p-6 h-full min-h-0 flex flex-col gap-6">
      {/* Control Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        {/* Timeframe Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground mr-2">Time Range:</span>
          <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
            {(['5m', '1h', '1d', 'all'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  timeframe === tf
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tf === 'all' ? 'All' : tf.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Display Mode Toggle */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground mr-2">Display:</span>
          <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
            <button
              onClick={() => setDisplayMode('absolute')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                displayMode === 'absolute'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              $ Absolute
            </button>
            <button
              onClick={() => setDisplayMode('percentage')}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                displayMode === 'percentage'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              % Change
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-4">
        <div className="flex-1 relative min-h-[320px]">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-muted-foreground">Loading...</div>
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height="100%" style={{ outline: 'none' }}>
                <LineChart
                  data={chartData}
                  margin={{ top: 20, right: 160, left: 20, bottom: 40 }}
                  onClick={handleChartClick}
                  onMouseLeave={() => setHoveredAccountId(null)}
                  style={{ outline: 'none' }}
                  tabIndex={-1}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" strokeWidth={0.5} />
                  <XAxis
                    dataKey="formattedTime"
                    stroke="#333333"
                    fontSize={12}
                    interval={Math.ceil(chartData.length / 6)}
                  />
                  <YAxis
                    stroke="#333333"
                    fontSize={12}
                    domain={yAxisDomain}
                    tickFormatter={(value) => 
                      displayMode === 'percentage' 
                        ? `${Number(value).toFixed(1)}%`
                        : `$${Number(value).toLocaleString('en-US')}`
                    }
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e5e5e5',
                      borderRadius: '6px',
                      color: '#333333',
                      fontSize: '12px'
                    }}
                    formatter={(value: any, name: string) => [
                      displayMode === 'percentage'
                        ? `${Number(value).toFixed(2)}%`
                        : `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
                      (name || 'NA').replace('default_', '').toUpperCase()
                    ]}
                    labelFormatter={(label: string) => label}
                  />
                  {uniqueUsers
                    .filter(username => {
                      const account = accountSummaries.find(acc => acc.username === username)
                      if (!account?.accountId) return false
                      if (hiddenAccounts.has(account.accountId)) return false
                      if (activeLegendAccountId && account.accountId !== activeLegendAccountId) return false
                      return true
                    })
                    .map((username) => {
                      const meta = accountMeta.get(username)
                      const color = meta?.color || '#666666'
                      const accountId = meta?.accountId
                      const isHovered = hoveredAccountId === accountId
                      const isHighlighted = !hoveredAccountId || isHovered

                      return (
                        <Line
                          key={username}
                          type="monotone"
                          dataKey={username}
                          stroke={color}
                          strokeWidth={isHighlighted ? 2.5 : 1}
                          dot={renderTerminalDot(username, color)}
                          activeDot={false}
                          connectNulls={false}
                          name={(username || 'NA').replace('default_', '').toUpperCase()}
                          strokeOpacity={isHighlighted ? 1 : 0.3}
                          isAnimationActive={false}
                          onMouseEnter={() => accountId && setHoveredAccountId(accountId)}
                          onMouseLeave={() => setHoveredAccountId(null)}
                          onClick={() => accountId && handleLegendClick(accountId)}
                        />
                      )
                    })}
                </LineChart>
              </ResponsiveContainer>
            </>
          )}
        </div>
      </div>


      {/* AI Trader Asset Ranking - Interactive Legend */}
      <div className="mt-6">
        <div className="text-xs font-medium mb-3 text-secondary-foreground flex items-center gap-2">
          <span>AI Trader Asset Ranking</span>
          <span className="text-[10px] text-muted-foreground">(Click to show/hide)</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {rankedAccounts.map((account, index) => {
            const isHidden = account.accountId ? hiddenAccounts.has(account.accountId) : false
            const isMuted = highlightAccountId && highlightAccountId !== 'all' && account.accountId !== highlightAccountId
            const isActive = !isHidden && !isMuted
            
            return (
              <div
                key={account.username}
                onClick={() => account.accountId && toggleAccountVisibility(account.accountId)}
                className={`
                  relative bg-white dark:bg-background border-2 px-4 py-3 rounded-lg flex items-center gap-3 min-w-0
                  cursor-pointer transition-all duration-200
                  ${isHidden 
                    ? 'border-gray-300 dark:border-gray-700 opacity-40 hover:opacity-60' 
                    : 'border-gray-900 dark:border-gray-200 hover:shadow-md'
                  }
                  ${isActive ? 'ring-2 ring-primary/20' : ''}
                `}
                title={isHidden ? 'Click to show' : 'Click to hide'}
              >
                {account.logo ? (
                  <div
                    className="h-10 w-10 rounded-full flex items-center justify-center transition-opacity"
                    style={{ 
                      backgroundColor: account.logo.color || '#656565',
                      opacity: isHidden ? 0.5 : 1
                    }}
                  >
                    <img
                      src={account.logo.src}
                      alt={account.logo.alt}
                      className="h-8 w-8 rounded-full object-contain"
                      loading="lazy"
                    />
                  </div>
                ) : (
                  <div className={`h-10 w-10 rounded-full bg-background/60 flex items-center justify-center text-sm font-semibold text-secondary-foreground transition-opacity ${isHidden ? 'opacity-50' : ''}`}>
                    {(account.username || 'NA').slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div className={`min-w-0 transition-opacity ${isHidden || isMuted ? 'opacity-40' : ''}`}>
                  <div className="text-xs font-medium text-secondary-foreground">
                    {(account.username || 'NA').replace('default_', '').toUpperCase()}
                  </div>
                  <FlipNumber
                    value={account.assets}
                    prefix="$"
                    className="text-lg font-bold text-secondary-foreground inline-flex items-center"
                  />
                </div>
                <div className={`ml-auto text-xs font-semibold text-primary transition-opacity ${isHidden || isMuted ? 'opacity-40' : ''}`}>
                  #{index + 1}
                </div>
                {isHidden && (
                  <div className="absolute inset-0 flex items-center justify-center bg-background/80 rounded-lg">
                    <span className="text-xs font-medium text-muted-foreground">Hidden</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
