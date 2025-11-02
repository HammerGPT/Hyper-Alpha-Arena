import React, { useEffect, useState, useRef } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AlertCircle, Info, AlertTriangle, RefreshCw, Trash2, TrendingUp, Brain, Bug, Database } from 'lucide-react'
import { toast } from 'react-hot-toast'

interface LogEntry {
  timestamp: string
  level: string
  category: string
  message: string
  details?: Record<string, any>
}

interface LogStats {
  total_logs: number
  by_level: {
    INFO: number
    WARNING: number
    ERROR: number
  }
  by_category: {
    price_update: number
    ai_decision: number
    system_error: number
  }
}

interface SamplingPoolData {
  [symbol: string]: {
    samples: Array<{
      price: number
      timestamp: number
      datetime: string
    }>
    sample_count: number
    price_change_percent: number | null
  }
}

export default function SystemLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [samplingPool, setSamplingPool] = useState<SamplingPoolData>({})
  const [loading, setLoading] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [selectedLevel, setSelectedLevel] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<string>('logs')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch logs
  const fetchLogs = async () => {
    try {
      const params = new URLSearchParams()
      if (selectedLevel !== 'all') params.append('level', selectedLevel)
      if (selectedCategory !== 'all') params.append('category', selectedCategory)
      params.append('limit', '100')

      const response = await fetch(`/api/system-logs/?${params}`)
      const data = await response.json()
      setLogs(data.logs || [])
    } catch (error) {
      console.error('Failed to fetch logs:', error)
      toast.error('Failed to fetch system logs')
    }
  }

  // Fetch stats
  const fetchStats = async () => {
    try {
      const response = await fetch('/api/system-logs/stats')
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }

  // Fetch sampling pool data
  const fetchSamplingPool = async () => {
    try {
      const response = await fetch('/api/sampling/pool-details')
      const data = await response.json()
      setSamplingPool(data)
    } catch (error) {
      console.error('Failed to fetch sampling pool:', error)
    }
  }

  // Clear logs
  const clearLogs = async () => {
    if (!confirm('Are you sure you want to clear all logs?')) return

    try {
      await fetch('/api/system-logs/', { method: 'DELETE' })
      toast.success('Logs cleared')
      fetchLogs()
      fetchStats()
    } catch (error) {
      toast.error('Failed to clear logs')
    }
  }

  // Auto refresh
  useEffect(() => {
    if (autoRefresh) {
      refreshIntervalRef.current = setInterval(() => {
        if (activeTab === 'logs') {
          fetchLogs()
          fetchStats()
        } else if (activeTab === 'sampling') {
          fetchSamplingPool()
        }
      }, 60000) // Refresh every 60 seconds
    } else {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current)
        refreshIntervalRef.current = null
      }
    }

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current)
      }
    }
  }, [autoRefresh, selectedCategory, selectedLevel, activeTab])

  // Initial load
  useEffect(() => {
    if (activeTab === 'logs') {
      fetchLogs()
      fetchStats()
    } else if (activeTab === 'sampling') {
      fetchSamplingPool()
    }
  }, [selectedCategory, selectedLevel, activeTab])

  // Level icon and color
  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'ERROR':
        return <AlertCircle className="w-4 h-4 text-red-500" />
      case 'WARNING':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
      default:
        return <Info className="w-4 h-4 text-blue-500" />
    }
  }

  const getLevelBadgeVariant = (level: string): "default" | "secondary" | "destructive" | "outline" => {
    switch (level) {
      case 'ERROR':
        return 'destructive'
      case 'WARNING':
        return 'secondary'
      default:
        return 'outline'
    }
  }

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'price_update':
        return <TrendingUp className="w-4 h-4 text-green-500" />
      case 'ai_decision':
        return <Brain className="w-4 h-4 text-purple-500" />
      case 'system_error':
        return <Bug className="w-4 h-4 text-red-500" />
      default:
        return <Info className="w-4 h-4" />
    }
  }

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp)
      return date.toLocaleString('en-US', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    } catch {
      return timestamp
    }
  }

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">System Logs</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${autoRefresh ? 'animate-spin' : ''}`} />
            {autoRefresh ? 'Auto Refresh' : 'Manual'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (activeTab === 'logs') {
                fetchLogs()
                fetchStats()
              } else if (activeTab === 'sampling') {
                fetchSamplingPool()
              }
            }}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
          <Button variant="destructive" size="sm" onClick={clearLogs}>
            <Trash2 className="w-4 h-4 mr-2" />
            Clear
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Logs
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_logs}</div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Errors
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-500">
                {stats.by_level.ERROR}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Warnings
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-500">
                {stats.by_level.WARNING}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                AI Decisions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-purple-500">
                {stats.by_category.ai_decision}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="logs">System Logs</TabsTrigger>
          <TabsTrigger value="sampling">Sampling Pool</TabsTrigger>
        </TabsList>

        <TabsContent value="logs" className="space-y-4">
          {/* Filter Tabs */}
          <Card>
            <CardHeader>
              <CardTitle>Filters</CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs value={selectedCategory} onValueChange={setSelectedCategory}>
                <TabsList>
                  <TabsTrigger value="all">All</TabsTrigger>
                  <TabsTrigger value="ai_decision">AI Decisions</TabsTrigger>
                  <TabsTrigger value="system_error">System Errors</TabsTrigger>
                  <TabsTrigger value="price_update">Price Updates</TabsTrigger>
                </TabsList>
              </Tabs>

              <div className="mt-4 flex gap-2">
                <Button
                  variant={selectedLevel === 'all' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedLevel('all')}
                >
                  All Levels
                </Button>
                <Button
                  variant={selectedLevel === 'INFO' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedLevel('INFO')}
                >
                  <Info className="w-4 h-4 mr-1" />
                  INFO
                </Button>
                <Button
                  variant={selectedLevel === 'WARNING' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedLevel('WARNING')}
                >
                  <AlertTriangle className="w-4 h-4 mr-1" />
                  WARNING
                </Button>
                <Button
                  variant={selectedLevel === 'ERROR' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedLevel('ERROR')}
                >
                  <AlertCircle className="w-4 h-4 mr-1" />
                  ERROR
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Log List */}
          <Card>
            <CardHeader>
              <CardTitle>Log Details ({logs.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[600px] pr-4">
                {logs.length === 0 ? (
                  <div className="text-center text-muted-foreground py-8">
                    No logs found
                  </div>
                ) : (
                  <div className="space-y-2">
                    {logs.map((log, index) => (
                      <div
                        key={index}
                        className="border rounded-lg p-3 hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-start gap-2 flex-1">
                            <div className="mt-1">
                              {getLevelIcon(log.level)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge variant={getLevelBadgeVariant(log.level)}>
                                  {log.level}
                                </Badge>
                                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                                  {getCategoryIcon(log.category)}
                                  {log.category}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  {formatTimestamp(log.timestamp)}
                                </span>
                              </div>
                              <p className="text-sm break-words">{log.message}</p>
                              {log.details && Object.keys(log.details).length > 0 && (
                                <details className="mt-2">
                                  <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                                    View Details
                                  </summary>
                                  <pre className="mt-2 text-xs bg-muted p-2 rounded overflow-x-auto">
                                    {JSON.stringify(log.details, null, 2)}
                                  </pre>
                                </details>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sampling" className="space-y-4">
          {/* Sampling Pool Details */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5" />
                Sampling Pool Details
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[600px] pr-4">
                {Object.keys(samplingPool).length === 0 ? (
                  <div className="text-center text-muted-foreground py-8">
                    No sampling data available
                  </div>
                ) : (
                  <div className="space-y-6">
                    {Object.entries(samplingPool).map(([symbol, data]) => (
                      <Card key={symbol} className="border-l-4 border-l-blue-500">
                        <CardHeader className="pb-3">
                          <div className="flex items-center justify-between">
                            <CardTitle className="text-lg">{symbol}</CardTitle>
                            <div className="flex items-center gap-4">
                              <Badge variant="outline">
                                {data.sample_count} samples
                              </Badge>
                              {data.price_change_percent !== null && data.price_change_percent !== undefined && (
                                <Badge
                                  variant={data.price_change_percent >= 0 ? "default" : "destructive"}
                                  className={data.price_change_percent >= 0 ? "bg-green-500" : ""}
                                >
                                  {data.price_change_percent >= 0 ? '+' : ''}{data.price_change_percent.toFixed(2)}%
                                </Badge>
                              )}
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-2">
                            <div className="text-sm text-muted-foreground mb-3">
                              Samples (oldest to newest):
                            </div>
                            {data.samples.map((sample, index) => (
                              <div
                                key={index}
                                className="flex items-center justify-between p-2 bg-muted/30 rounded text-sm"
                              >
                                <span className="font-mono">
                                  ${sample.price.toFixed(6)}
                                </span>
                                <span className="text-muted-foreground">
                                  {formatTimestamp(sample.datetime)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
