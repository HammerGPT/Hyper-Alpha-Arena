import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions,
} from 'chart.js'
import { Card } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getModelLogo } from './logoAssets'
import FlipNumber from './FlipNumber'

// 注册Chart.js组件
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

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
}

type Timeframe = '5m' | '1h' | '1d'

interface ChartLabel {
  x: number
  y: number
  value: number
  color: string
  isMuted: boolean
  username: string
}

export default function AssetCurve({ data: initialData, wsRef, highlightAccountId }: AssetCurveProps) {
  const [timeframe, setTimeframe] = useState<Timeframe>('1h')
  const [data, setData] = useState<AssetCurveData[]>(initialData || [])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const logoCacheRef = useRef<Map<string, HTMLImageElement>>(new Map())
  const [chartLabels, setChartLabels] = useState<ChartLabel[]>([])
  const chartContainerRef = useRef<HTMLDivElement>(null)

  // Listen for WebSocket asset curve updates
  useEffect(() => {
    if (!wsRef?.current) return

    const handleMessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'asset_curve_data' && msg.timeframe === timeframe) {
          setData(msg.data || [])
          setLoading(false)
          setError(null)
          setIsInitialized(true)
        } else if (msg.type === 'asset_curve_update' && msg.timeframe === timeframe) {
          // Real-time update for current timeframe
          setData(msg.data || [])
          setIsInitialized(true)
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    }

    wsRef.current.addEventListener('message', handleMessage)
    
    return () => {
      wsRef.current?.removeEventListener('message', handleMessage)
    }
  }, [wsRef, timeframe])

  // Request data when timeframe changes
  useEffect(() => {
    if (wsRef?.current && wsRef.current.readyState === WebSocket.OPEN) {
      setLoading(true)
      setError(null)
      wsRef.current.send(JSON.stringify({
        type: 'get_asset_curve',
        timeframe: timeframe
      }))
    } else if (initialData && timeframe === '1h' && !isInitialized) {
      // Only use initial data on first mount, not on subsequent prop changes
      setData(initialData)
      setIsInitialized(true)
    }
  }, [timeframe, wsRef])

  // Initialize with initial data only once on first mount
  useEffect(() => {
    if (initialData && !isInitialized && timeframe === '1h') {
      setData(initialData)
      setIsInitialized(true)
    }
  }, []) // Empty dependency array - only run on mount

  // No more auto-refresh polling - rely on WebSocket asset_curve_update broadcasts (every 60s from backend)

  const handleTimeframeChange = (value: string) => {
    setTimeframe(value as Timeframe)
  }
  if (!data || data.length === 0) {
    return (
      <Card className="p-6">
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <Tabs value={timeframe} onValueChange={handleTimeframeChange}>
              <TabsList>
                <TabsTrigger value="5m">5 Minutes</TabsTrigger>
                <TabsTrigger value="1h">1 Hour</TabsTrigger>
                <TabsTrigger value="1d">1 Day</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <div className="flex items-center justify-center h-96">
            <div className="text-muted-foreground">
              {loading ? 'Loading...' : error || 'No asset data available'}
            </div>
          </div>
        </div>
      </Card>
    )
  }

  const getLogoImage = useCallback((src?: string) => {
    if (!src) return undefined
    const cache = logoCacheRef.current
    if (cache.has(src)) {
      return cache.get(src)
    }
    const img = new Image()
    img.src = src
    cache.set(src, img)
    return img
  }, [])

  const colors = [
    'rgb(59, 130, 246)',   // blue
    'rgb(34, 197, 94)',     // green
    'rgb(168, 85, 247)',    // purple
    'rgb(239, 68, 68)',     // red
    'rgb(245, 158, 11)',    // orange
    'rgb(16, 185, 129)',    // emerald
    'rgb(139, 92, 246)',    // violet
    'rgb(236, 72, 153)',    // pink
  ]

  const toRgba = (color: string, alpha: number) =>
    color.replace('rgb', 'rgba').replace(')', `, ${alpha})`)

  const highlightActive = highlightAccountId !== undefined && highlightAccountId !== 'all'

  const {
    chartData,
    accountSummaries,
    accountByUsername,
  } = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        chartData: { labels: [], datasets: [] },
        accountSummaries: [] as { username: string; assets: number; accountId?: number; logo?: { src: string; alt: string } }[],
        accountByUsername: new Map<string, number>(),
      }
    }

    const groupedData = data.reduce((acc, item) => {
      const key = item.datetime_str || item.date || item.timestamp?.toString() || ''
      if (!acc[key]) {
        acc[key] = {}
      }
      acc[key][item.username] = item.total_assets
      return acc
    }, {} as Record<string, Record<string, number>>)

    const timestamps = Object.keys(groupedData).sort()
    const uniqueUsers = Array.from(new Set(data.map(item => item.username))).sort()

    const accountMap = new Map<string, number>()
    data.forEach((item) => {
      if (!accountMap.has(item.username)) {
        accountMap.set(item.username, item.account_id)
      }
    })

    const datasets = uniqueUsers.map((username, index) => {
      const baseColor = colors[index % colors.length]
      const currentAccountId = accountMap.get(username)
      const isHighlighted = !highlightActive || currentAccountId === highlightAccountId
      const logoInfo = getModelLogo(username)
      const logoImage = getLogoImage(logoInfo?.src)

      const values = timestamps.map(ts => groupedData[ts][username] ?? null)
      const latestValue = values.reduce<number | null>((acc, value) => {
        if (value !== null && value !== undefined) {
          return value
        }
        return acc
      }, null)

      return {
        label: username.replace('default_', '').toUpperCase(),
        data: values,
        borderColor: isHighlighted ? baseColor : toRgba(baseColor, 0.25),
        backgroundColor: isHighlighted ? toRgba(baseColor, 0.15) : toRgba(baseColor, 0.05),
        borderWidth: isHighlighted ? 3 : 1.5,
        fill: false,
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: isHighlighted ? 5 : 0,
        spanGaps: true,
        order: isHighlighted ? 0 : 1,
        pointHitRadius: 12,
        customMeta: {
          username,
          latestValue: latestValue ?? 0,
          logoImage,
          logoInfo,
          color: baseColor,
          accountId: currentAccountId,
          isHighlighted,
          isMuted: highlightActive && currentAccountId !== highlightAccountId,
        },
      }
    })

    const summaries = uniqueUsers
      .map(username => {
        const latestData = data
          .filter(item => item.username === username)
          .sort((a, b) => {
            const dateA = new Date(a.datetime_str || a.date || 0).getTime()
            const dateB = new Date(b.datetime_str || b.date || 0).getTime()
            return dateB - dateA
          })[0]
        return {
          username,
          assets: latestData?.total_assets || 0,
          accountId: accountMap.get(username),
          logo: getModelLogo(username),
        }
      })

    return {
      chartData: {
        labels: timestamps.map((timestamp) => {
          const d = new Date(timestamp)
          if (timeframe === '5m') {
            return d.toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
            })
          } else if (timeframe === '1h') {
            return d.toLocaleString('en-US', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
            })
          }
          return d.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })
        }),
        datasets,
      },
      accountSummaries: summaries,
      accountByUsername: accountMap,
    }
  }, [data, timeframe, highlightActive, highlightAccountId, getLogoImage])

  const rankedAccounts = useMemo(
    () => accountSummaries.slice().sort((a, b) => b.assets - a.assets),
    [accountSummaries]
  )

  const endpointPlugin = useMemo(() => {
    return {
      id: 'dataset-endpoint-logo',
      afterDatasetsDraw(chart: ChartJS) {
        const { ctx, data: chartDataset, chartArea } = chart
        if (!chartDataset.datasets.length) return

        const style = getComputedStyle(ctx.canvas)
        const fallbackTextColor = style.getPropertyValue('--foreground') || style.color || '#0f172a'
        const mutedTextColor = style.getPropertyValue('--muted-foreground') || 'rgba(148, 163, 184, 0.9)'

        const labels: ChartLabel[] = []

        chartDataset.datasets.forEach((dataset: any, datasetIndex: number) => {
          const meta = chart.getDatasetMeta(datasetIndex)
          if (!chart.isDatasetVisible(datasetIndex)) return
          if (!meta?.data?.length) return

          const point = meta.data[meta.data.length - 1]
          if (!point) return
          const props = point.getProps(['x', 'y'], true)
          const { x, y } = props
          if (Number.isNaN(x) || Number.isNaN(y)) return

          const customMeta = dataset.customMeta || {}
          const {
            logoImage,
            color,
            latestValue,
            isMuted,
            isHighlighted,
          } = customMeta

          const radius = isHighlighted ? 15 : 13

          ctx.save()
          ctx.beginPath()
          ctx.arc(x, y, radius, 0, Math.PI * 2)
          ctx.fillStyle = isMuted ? 'rgba(148, 163, 184, 0.15)' : toRgba(color || 'rgb(59, 130, 246)', 0.2)
          ctx.fill()
          ctx.lineWidth = isHighlighted ? 3 : 1.5
          ctx.strokeStyle = color || 'rgb(59, 130, 246)'
          ctx.stroke()

          if (logoImage) {
            if (!logoImage.complete) {
              logoImage.onload = () => {
                chart.draw()
              }
            } else {
              ctx.save()
              ctx.beginPath()
              ctx.arc(x, y, radius - 2, 0, Math.PI * 2)
              ctx.clip()
              ctx.drawImage(logoImage, x - (radius - 2), y - (radius - 2), (radius - 2) * 2, (radius - 2) * 2)
              ctx.restore()
            }
          }
          ctx.restore()

          // Save label position for HTML overlay instead of canvas drawing
          if (typeof latestValue === 'number') {
            const activeColor = color || 'rgb(59, 130, 246)'
            labels.push({
              x: x + radius + 14,
              y: y,
              value: latestValue,
              color: activeColor,
              isMuted: isMuted || false,
              username: dataset.label || '',
            })
          }
        })

        // Update chartLabels state with new positions
        setChartLabels(labels)
      },
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartData])

  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    layout: {
      padding: {
        right: 220,
      },
    },
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: false,
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: (context) => {
            const label = context.dataset.label || ''
            const value = context.parsed.y
            return `${label}: $${value?.toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2
            })}`
          },
        },
      },
    },
    scales: {
      x: {
        display: true,
        title: {
          display: true,
          text: 'Date',
        },
      },
      y: {
        display: true,
        title: {
          display: true,
          text: 'Amount (USD)',
        },
        ticks: {
          callback: function(value) {
            return '$' + Number(value).toLocaleString('en-US')
          },
        },
      },
    },
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false,
    },
  }

  return (
    <div className="p-6 h-full flex flex-col gap-6">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <Tabs value={timeframe} onValueChange={handleTimeframeChange}>
            <TabsList>
              <TabsTrigger value="5m">5 Minutes</TabsTrigger>
              <TabsTrigger value="1h">1 Hour</TabsTrigger>
              <TabsTrigger value="1d">1 Day</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <div className="h-[calc(80vh-10rem)] relative" ref={chartContainerRef}>
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-muted-foreground">Loading...</div>
            </div>
          ) : (
            <>
              <Line data={chartData} options={options} plugins={[endpointPlugin]} />
              {/* HTML overlay for flip number labels */}
              <div className="absolute inset-0 pointer-events-none">
                {chartLabels.map((label, index) => {
                  const backgroundColor = label.isMuted
                    ? 'rgba(148, 163, 184, 0.25)'
                    : toRgba(label.color, 0.9)
                  const textColor = label.isMuted ? 'rgb(148, 163, 184)' : '#ffffff'

                  return (
                    <div
                      key={`${label.username}-${index}`}
                      className="absolute"
                      style={{
                        left: `${label.x}px`,
                        top: `${label.y}px`,
                        transform: 'translateY(-50%)',
                        backgroundColor,
                        color: textColor,
                        padding: '4px 12px',
                        borderRadius: '8px',
                        fontSize: '12px',
                        fontFamily: '"JetBrains Mono", monospace',
                      }}
                    >
                      <FlipNumber value={label.value} prefix="$" decimals={2} />
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Account Asset Ranking */}
      <div className="mt-6">
        <div className="text-xs font-medium mb-3 text-secondary-foreground">Account Asset Ranking</div>
        <div className="flex flex-wrap gap-3">
          {rankedAccounts.map((account, index) => {
            const accountId = accountByUsername.get(account.username)
            const isMuted = highlightActive && accountId !== highlightAccountId
            return (
              <div
                key={account.username}
                className="bg-white dark:bg-background border-2 border-gray-900 dark:border-gray-200 px-4 py-3 rounded-lg flex items-center gap-3"
              >
                {account.logo ? (
                  <img
                    src={account.logo.src}
                    alt={account.logo.alt}
                    className="h-10 w-10 rounded-full object-contain bg-background"
                    loading="lazy"
                  />
                ) : (
                  <div className="h-10 w-10 rounded-full bg-background/60 flex items-center justify-center text-sm font-semibold text-secondary-foreground">
                    {account.username.slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div className={`transition-opacity ${isMuted ? 'opacity-40' : ''}`}>
                  <div className="text-xs font-medium text-secondary-foreground">
                    {account.username.replace('default_', '').toUpperCase()}
                  </div>
                  <FlipNumber
                    value={account.assets}
                    prefix="$"
                    className="text-lg font-bold text-secondary-foreground inline-flex items-center"
                  />
                </div>
                <div className={`ml-auto text-xs font-semibold text-primary transition-opacity ${isMuted ? 'opacity-40' : ''}`}>#{index + 1}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
