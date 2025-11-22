import { useState, useEffect, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import TradingViewChart from './TradingViewChart'
import PacmanLoader from '../ui/pacman-loader'

interface KlinesViewProps {
  onAccountUpdated?: () => void
}

interface MarketData {
  symbol: string
  price: number
  change24h: number
  volume24h: number
}

interface BackfillTask {
  task_id: number
  symbol: string
  status: string
  progress: number
  total_records: number
  collected_records: number
}

export default function KlinesView({ onAccountUpdated }: KlinesViewProps) {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC')
  const [selectedPeriod, setSelectedPeriod] = useState<string>('1m')
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([])
  const [marketData, setMarketData] = useState<MarketData[]>([])
  const [currentTask, setCurrentTask] = useState<BackfillTask | null>(null)
  const [loading, setLoading] = useState(false)
  const [isPageVisible, setIsPageVisible] = useState(true)

  const marketDataIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const taskCheckIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // 页面可见性监听
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsPageVisible(!document.hidden)
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  // 获取 watchlist
  useEffect(() => {
    fetchWatchlist()
  }, [])

  // 获取市场数据
  useEffect(() => {
    if (watchlistSymbols.length > 0 && isPageVisible) {
      fetchMarketData()
      marketDataIntervalRef.current = setInterval(fetchMarketData, 60000) // 改为60秒
    }

    return () => {
      if (marketDataIntervalRef.current) {
        clearInterval(marketDataIntervalRef.current)
        marketDataIntervalRef.current = null
      }
    }
  }, [watchlistSymbols, isPageVisible])

  // 轮询当前任务状态
  useEffect(() => {
    if (isPageVisible) {
      checkCurrentTask()
      taskCheckIntervalRef.current = setInterval(checkCurrentTask, 10000) // 改为10秒检查一次
    }

    return () => {
      if (taskCheckIntervalRef.current) {
        clearInterval(taskCheckIntervalRef.current)
        taskCheckIntervalRef.current = null
      }
    }
  }, [isPageVisible])

  // 组件卸载时清理所有定时器
  useEffect(() => {
    return () => {
      if (marketDataIntervalRef.current) {
        clearInterval(marketDataIntervalRef.current)
      }
      if (taskCheckIntervalRef.current) {
        clearInterval(taskCheckIntervalRef.current)
      }
    }
  }, [])

  const fetchWatchlist = async () => {
    try {
      const response = await fetch('/api/hyperliquid/symbols/watchlist')
      const data = await response.json()
      const symbols = data.symbols || []
      setWatchlistSymbols(symbols)
      if (symbols.length > 0 && !symbols.includes(selectedSymbol)) {
        setSelectedSymbol(symbols[0])
      }
    } catch (error) {
      console.error('Failed to fetch watchlist:', error)
    }
  }

  const fetchMarketData = async () => {
    try {
      const symbolsParam = watchlistSymbols.join(',')
      if (!symbolsParam) return

      const response = await fetch(`/api/market/prices?symbols=${symbolsParam}`)
      if (!response.ok) return

      const data = await response.json()
      const formattedData = data.map((item: any) => ({
        symbol: item.symbol,
        price: item.price || 0,
        change24h: 0,
        volume24h: 0
      }))
      setMarketData(formattedData)
    } catch (error) {
      console.error('Failed to fetch market data:', error)
    }
  }

  const checkCurrentTask = async () => {
    try {
      const response = await fetch('/api/klines/backfill-tasks')
      const data = await response.json()
      const tasks = data.tasks || []

      // 找到正在运行或等待的任务
      const activeTask = tasks.find((t: BackfillTask) =>
        t.status === 'running' || t.status === 'pending'
      )

      if (activeTask) {
        setCurrentTask(activeTask)
      } else {
        // 检查是否有刚完成的任务需要删除
        const completedTask = tasks.find((t: BackfillTask) => t.status === 'completed')
        if (completedTask && currentTask?.task_id === completedTask.task_id) {
          // 删除已完成的任务
          await fetch(`/api/klines/backfill-tasks/${completedTask.task_id}`, {
            method: 'DELETE'
          }).catch(() => {}) // 忽略删除错误
        }
        setCurrentTask(null)
      }
    } catch (error) {
      console.error('Failed to check task status:', error)
    }
  }

  const handleBackfill = async () => {
    if (!selectedSymbol || loading || currentTask) return

    setLoading(true)
    try {
      const endTime = new Date()
      const startTime = new Date()
      startTime.setDate(startTime.getDate() - 30)

      const response = await fetch('/api/klines/backfill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbols: [selectedSymbol],
          start_time: startTime.toISOString(),
          end_time: endTime.toISOString(),
          period: '1m'
        })
      })

      if (response.ok) {
        // 立即检查任务状态
        setTimeout(checkCurrentTask, 500)
      }
    } catch (error) {
      console.error('Failed to start backfill:', error)
    } finally {
      setLoading(false)
    }
  }

  const getSymbolMarketData = (symbol: string) => {
    return marketData.find(data => data.symbol === symbol)
  }

  // 渲染按钮或进度条
  const renderBackfillButton = () => {
    if (currentTask) {
      const progress = currentTask.progress || 0
      const collected = currentTask.collected_records || 0
      const total = currentTask.total_records || 0

      return (
        <div className="w-full space-y-1">
          <div className="relative w-full h-8 bg-muted rounded-md overflow-hidden">
            {/* 进度条背景 */}
            <div
              className="absolute inset-y-0 left-0 bg-primary/80 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
            {/* 进度文字 */}
            <div className="absolute inset-0 flex items-center justify-center text-xs font-medium">
              <span className={progress > 50 ? 'text-primary-foreground' : 'text-foreground'}>
                {currentTask.symbol} ({collected}/{total}) {progress}%
              </span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground text-center">
            Backfilling in progress...
          </p>
        </div>
      )
    }

    return (
      <div className="space-y-2">
        <Button
          onClick={handleBackfill}
          disabled={loading}
          className="w-full"
          size="sm"
        >
          {loading ? 'Starting...' : 'Backfill Historical Data'}
        </Button>
        <p className="text-xs text-muted-foreground">
          Backfill last 30 days of K-line data
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Symbol Selection and Market Data */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 flex-shrink-0">
        {/* Symbol and Period Selection */}
        <Card>
          <CardContent className="pt-4 space-y-3">
            {/* Symbol and Period in one row */}
            <div className="flex items-center gap-2">
              <Select value={selectedSymbol} onValueChange={setSelectedSymbol}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Select Symbol" />
                </SelectTrigger>
                <SelectContent>
                  {watchlistSymbols.map(symbol => (
                    <SelectItem key={symbol} value={symbol}>
                      {symbol}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1m">1m</SelectItem>
                  <SelectItem value="3m">3m</SelectItem>
                  <SelectItem value="5m">5m</SelectItem>
                  <SelectItem value="15m">15m</SelectItem>
                  <SelectItem value="30m">30m</SelectItem>
                  <SelectItem value="1h">1h</SelectItem>
                  <SelectItem value="2h">2h</SelectItem>
                  <SelectItem value="4h">4h</SelectItem>
                  <SelectItem value="8h">8h</SelectItem>
                  <SelectItem value="12h">12h</SelectItem>
                  <SelectItem value="1d">1d</SelectItem>
                  <SelectItem value="3d">3d</SelectItem>
                  <SelectItem value="1w">1w</SelectItem>
                  <SelectItem value="1M">1M</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {selectedSymbol && renderBackfillButton()}
          </CardContent>
        </Card>

        {/* Market Data */}
        <Card className="lg:col-span-3">
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Market Data</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {selectedSymbol && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {(() => {
                  const data = getSymbolMarketData(selectedSymbol)
                  return data ? (
                    <>
                      <div>
                        <p className="text-xs text-muted-foreground">Current Price</p>
                        <p className="text-lg font-semibold">${data.price.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">24h Change</p>
                        <p className={`text-lg font-semibold ${data.change24h >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {data.change24h >= 0 ? '+' : ''}{data.change24h.toFixed(2)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">24h Volume</p>
                        <p className="text-lg font-semibold">${data.volume24h.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Data Status</p>
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                          <span className="text-sm">Live Updates</span>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="col-span-4 text-center text-muted-foreground">
                      <div className="flex items-center justify-center gap-2">
                        <PacmanLoader className="w-12 h-6" />
                        Loading market data...
                      </div>
                    </div>
                  )
                })()}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* K-Line Chart Area - 动态高度铺满剩余空间 */}
      <Card className="flex-1 min-h-0">
        <CardHeader className="py-3">
          <CardTitle className="text-sm">
            {selectedSymbol} K-Line Chart ({selectedPeriod})
          </CardTitle>
        </CardHeader>
        <CardContent className="h-[calc(100%-3rem)] pb-4">
          <TradingViewChart
            symbol={selectedSymbol}
            period={selectedPeriod}
          />
        </CardContent>
      </Card>
    </div>
  )
}
