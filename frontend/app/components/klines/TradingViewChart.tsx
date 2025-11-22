import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries } from 'lightweight-charts'
import PacmanLoader from '../ui/pacman-loader'
import { formatChartTime } from '../../lib/dateTime'

interface TradingViewChartProps {
  symbol: string
  period: string
  data?: any[]
  onLoadMore?: () => void
}

export default function TradingViewChart({ symbol, period, data = [], onLoadMore }: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const seriesRef = useRef<any>(null)
  const [loading, setLoading] = useState(false)
  const [hasData, setHasData] = useState(false)

  // 初始化图表
  useEffect(() => {
    if (!chartContainerRef.current) return

    try {
      const container = chartContainerRef.current

      // 创建图表 - 动态获取容器尺寸
      const chart = createChart(container, {
        width: container.clientWidth,
        height: container.clientHeight || 400,
        layout: {
          background: { color: 'transparent' },
          textColor: '#9ca3af',
          attributionLogo: false, // 隐藏 TradingView logo
        },
        grid: {
          vertLines: { color: 'rgba(156, 163, 175, 0.1)' },
          horzLines: { color: 'rgba(156, 163, 175, 0.1)' },
        },
        crosshair: {
          mode: 0,
        },
        rightPriceScale: {
          borderColor: 'rgba(156, 163, 175, 0.2)',
        },
        timeScale: {
          borderColor: 'rgba(156, 163, 175, 0.2)',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      // 创建K线系列
      const candlestickSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderDownColor: '#ef4444',
        borderUpColor: '#22c55e',
        wickDownColor: '#ef4444',
        wickUpColor: '#22c55e',
      })

      chartRef.current = chart
      seriesRef.current = candlestickSeries

      // 监听容器大小变化
      const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
          const { width, height } = entry.contentRect
          if (chartRef.current && width > 0 && height > 0) {
            chartRef.current.applyOptions({ width, height })
          }
        }
      })
      resizeObserver.observe(container)

      return () => {
        resizeObserver.disconnect()
        chart.remove()
        chartRef.current = null
        seriesRef.current = null
      }
    } catch (error) {
      console.error('Chart initialization failed:', error)
    }
  }, [])

  // 更新数据
  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      seriesRef.current.setData(data)

      if (chartRef.current) {
        chartRef.current.timeScale().fitContent()
      }
    }
  }, [data])

  // 获取K线数据
  const fetchKlineData = async () => {
    if (loading) return

    setLoading(true)
    try {
      const response = await fetch(`/api/market/kline/${symbol}?market=hyperliquid&period=${period}&count=500`)
      const result = await response.json()

      if (result.data && result.data.length > 0) {
        const chartData = result.data.map((item: any) => ({
          time: formatChartTime(item.timestamp),
          open: item.open || 0,
          high: item.high || 0,
          low: item.low || 0,
          close: item.close || 0,
        }))

        if (seriesRef.current) {
          try {
            seriesRef.current.setData(chartData)
            setHasData(true)
            if (chartRef.current && chartRef.current.timeScale) {
              chartRef.current.timeScale().fitContent()
            }
          } catch (e) {
            console.error('Failed to set chart data:', e)
          }
        }
      } else {
        setHasData(false)
      }
    } catch (error) {
      console.error('Failed to fetch kline data:', error)
      setHasData(false)
    } finally {
      setLoading(false)
    }
  }

  // 当symbol或period变化时重新获取数据
  useEffect(() => {
    if (symbol && period) {
      // 清空旧数据，显示loading状态
      setHasData(false)
      if (seriesRef.current) {
        seriesRef.current.setData([])
      }
      fetchKlineData()
    }
  }, [symbol, period])

  return (
    <div className="relative w-full h-full">
      {/* 图表容器 - 铺满父元素 */}
      <div ref={chartContainerRef} className="w-full h-full" />

      {/* 自定义水印 */}
      <div className="absolute bottom-2 right-2 text-xs text-muted-foreground/30 pointer-events-none select-none">
        Hyper Alpha Arena
      </div>

      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/50">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <PacmanLoader className="w-12 h-6" />
            Loading K-line data...
          </div>
        </div>
      )}

      {!loading && !hasData && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <p className="text-lg font-medium">No K-line data available</p>
            <p className="text-sm">Click "Backfill Historical Data" to fetch data</p>
          </div>
        </div>
      )}
    </div>
  )
}
