import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries } from 'lightweight-charts'
import PacmanLoader from '../ui/pacman-loader'
import { formatChartTime } from '../../lib/dateTime'

interface TradingViewChartProps {
  symbol: string
  period: string
  data?: any[]
  onLoadMore?: () => void
}

type ChartType = 'candlestick' | 'line' | 'area'

export default function TradingViewChart({ symbol, period, data = [], onLoadMore }: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const seriesRef = useRef<any>(null)
  const volumeSeriesRef = useRef<any>(null)
  const ma5SeriesRef = useRef<any>(null)
  const ma10SeriesRef = useRef<any>(null)
  const ma20SeriesRef = useRef<any>(null)
  const [loading, setLoading] = useState(false)
  const [hasData, setHasData] = useState(false)
  const [chartType, setChartType] = useState<ChartType>('candlestick')
  const [chartData, setChartData] = useState<any[]>([])
  const [showMA, setShowMA] = useState({ ma5: false, ma10: false, ma20: false })

  // 创建主图表系列
  const createMainSeries = (chart: any, type: ChartType) => {
    switch (type) {
      case 'candlestick':
        return chart.addSeries(CandlestickSeries, {
          upColor: '#22c55e',
          downColor: '#ef4444',
          borderDownColor: '#ef4444',
          borderUpColor: '#22c55e',
          wickDownColor: '#ef4444',
          wickUpColor: '#22c55e',
        })
      case 'line':
        return chart.addSeries(LineSeries, {
          color: '#3b82f6',
          lineWidth: 2,
        })
      case 'area':
        return chart.addSeries(AreaSeries, {
          topColor: '#3b82f640',
          bottomColor: '#3b82f610',
          lineColor: '#3b82f6',
          lineWidth: 2,
        })
      default:
        return chart.addSeries(CandlestickSeries, {
          upColor: '#22c55e',
          downColor: '#ef4444',
          borderDownColor: '#ef4444',
          borderUpColor: '#22c55e',
          wickDownColor: '#ef4444',
          wickUpColor: '#22c55e',
        })
    }
  }

  // 转换数据格式
  const convertDataForSeries = (data: any[], type: ChartType) => {
    switch (type) {
      case 'candlestick':
        return data.map(item => ({
          time: item.time,
          open: item.open,
          high: item.high,
          low: item.low,
          close: item.close,
        }))
      case 'line':
      case 'area':
        return data.map(item => ({
          time: item.time,
          value: item.close,
        }))
      default:
        return data
    }
  }

  // 计算移动平均线
  const calculateMA = (data: any[], period: number) => {
    const result = []
    for (let i = period - 1; i < data.length; i++) {
      const sum = data.slice(i - period + 1, i + 1).reduce((acc, item) => acc + item.close, 0)
      result.push({
        time: data[i].time,
        value: sum / period,
      })
    }
    return result
  }

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
        localization: {
          locale: 'en-US',
        },
        grid: {
          vertLines: { color: 'rgba(156, 163, 175, 0.1)' },
          horzLines: { color: 'rgba(156, 163, 175, 0.1)' },
        },
        crosshair: {
          mode: 1, // 启用更详细的十字线模式
          vertLine: {
            width: 1,
            color: 'rgba(156, 163, 175, 0.5)',
            style: 0,
          },
          horzLine: {
            width: 1,
            color: 'rgba(156, 163, 175, 0.5)',
            style: 0,
          },
        },
        rightPriceScale: {
          borderColor: 'rgba(156, 163, 175, 0.2)',
        },
        timeScale: {
          borderColor: 'rgba(156, 163, 175, 0.2)',
          timeVisible: true,
          secondsVisible: false,
        },
        pane: {
          separatorColor: 'rgba(156, 163, 175, 0.3)',
        },
      })

      // 创建主图表系列
      const mainSeries = createMainSeries(chart, chartType)

      // 创建成交量系列（独立Pane）
      const volumeSeries = chart.addSeries(HistogramSeries, {
        color: '#6b7280',
        priceFormat: {
          type: 'volume',
        },
      }, 1) // 使用独立的pane (1)


      // 创建移动平均线系列
      const ma5Series = chart.addSeries(LineSeries, {
        color: '#ff6b6b',
        lineWidth: 1,
        visible: false,
      })

      const ma10Series = chart.addSeries(LineSeries, {
        color: '#4ecdc4',
        lineWidth: 1,
        visible: false,
      })

      const ma20Series = chart.addSeries(LineSeries, {
        color: '#45b7d1',
        lineWidth: 1,
        visible: false,
      })

      chartRef.current = chart
      seriesRef.current = mainSeries
      volumeSeriesRef.current = volumeSeries
      ma5SeriesRef.current = ma5Series
      ma10SeriesRef.current = ma10Series
      ma20SeriesRef.current = ma20Series

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
        volumeSeriesRef.current = null
        ma5SeriesRef.current = null
        ma10SeriesRef.current = null
        ma20SeriesRef.current = null
      }
    } catch (error) {
      console.error('Chart initialization failed:', error)
    }
  }, [chartType])

  // 更新数据
  useEffect(() => {
    if (seriesRef.current && volumeSeriesRef.current && chartData.length > 0) {
      // 转换主图数据
      const mainData = convertDataForSeries(chartData, chartType)

      // 成交量数据
      const volumeData = chartData.map(item => ({
        time: item.time,
        value: item.volume || 0,
        color: item.close >= item.open ? '#22c55e40' : '#ef444440',
      }))

      // 移动平均线数据
      const ma5Data = calculateMA(chartData, 5)
      const ma10Data = calculateMA(chartData, 10)
      const ma20Data = calculateMA(chartData, 20)

      seriesRef.current.setData(mainData)
      volumeSeriesRef.current.setData(volumeData)

      if (ma5SeriesRef.current) ma5SeriesRef.current.setData(ma5Data)
      if (ma10SeriesRef.current) ma10SeriesRef.current.setData(ma10Data)
      if (ma20SeriesRef.current) ma20SeriesRef.current.setData(ma20Data)

      if (chartRef.current) {
        chartRef.current.timeScale().fitContent()
      }
    }
  }, [chartData, chartType])

  // 控制移动平均线显示/隐藏
  useEffect(() => {
    if (ma5SeriesRef.current) {
      ma5SeriesRef.current.applyOptions({ visible: showMA.ma5 })
    }
    if (ma10SeriesRef.current) {
      ma10SeriesRef.current.applyOptions({ visible: showMA.ma10 })
    }
    if (ma20SeriesRef.current) {
      ma20SeriesRef.current.applyOptions({ visible: showMA.ma20 })
    }
  }, [showMA])

  // 获取K线数据
  const fetchKlineData = async () => {
    if (loading) return

    setLoading(true)
    try {
      const response = await fetch(`/api/market/kline/${symbol}?market=hyperliquid&period=${period}&count=500`)
      const result = await response.json()

      if (result.data && result.data.length > 0) {
        const newChartData = result.data.map((item: any) => ({
          time: formatChartTime(item.timestamp),
          open: item.open || 0,
          high: item.high || 0,
          low: item.low || 0,
          close: item.close || 0,
          volume: item.volume || 0,
        }))

        setChartData(newChartData)

        setHasData(true)
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
      // 立即清空图表数据，显示loading状态
      setHasData(false)
      setChartData([])

      // 直接清空所有图表系列数据，避免loading与旧数据混合
      if (seriesRef.current) {
        seriesRef.current.setData([])
      }
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.setData([])
      }
      if (ma5SeriesRef.current) {
        ma5SeriesRef.current.setData([])
      }
      if (ma10SeriesRef.current) {
        ma10SeriesRef.current.setData([])
      }
      if (ma20SeriesRef.current) {
        ma20SeriesRef.current.setData([])
      }

      fetchKlineData()
    }
  }, [symbol, period])

  return (
    <div className="relative w-full h-full">
      {/* 图表类型切换器 */}
      <div className="absolute top-2 left-2 z-10 flex gap-1 bg-background/80 backdrop-blur-sm rounded-md p-1 border">
        <button
          onClick={() => setChartType('candlestick')}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            chartType === 'candlestick'
              ? 'bg-primary text-primary-foreground'
              : 'hover:bg-muted'
          }`}
        >
          Candlestick
        </button>
        <button
          onClick={() => setChartType('line')}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            chartType === 'line'
              ? 'bg-primary text-primary-foreground'
              : 'hover:bg-muted'
          }`}
        >
          Line
        </button>
        <button
          onClick={() => setChartType('area')}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            chartType === 'area'
              ? 'bg-primary text-primary-foreground'
              : 'hover:bg-muted'
          }`}
        >
          Area
        </button>
      </div>

      {/* 移动平均线控制器 */}
      <div className="absolute top-2 right-2 z-10 flex gap-1 bg-background/80 backdrop-blur-sm rounded-md p-1 border">
        <button
          onClick={() => setShowMA(prev => ({ ...prev, ma5: !prev.ma5 }))}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            showMA.ma5
              ? 'bg-red-500/20 text-red-400 border border-red-500/30'
              : 'hover:bg-muted'
          }`}
        >
          MA5
        </button>
        <button
          onClick={() => setShowMA(prev => ({ ...prev, ma10: !prev.ma10 }))}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            showMA.ma10
              ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30'
              : 'hover:bg-muted'
          }`}
        >
          MA10
        </button>
        <button
          onClick={() => setShowMA(prev => ({ ...prev, ma20: !prev.ma20 }))}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            showMA.ma20
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'hover:bg-muted'
          }`}
        >
          MA20
        </button>
      </div>

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
