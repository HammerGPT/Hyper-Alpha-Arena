import React, { useEffect, useState, useRef } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AlertCircle, Info, AlertTriangle, RefreshCw, Trash2, TrendingUp, Brain, Bug } from 'lucide-react'
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

export default function SystemLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [selectedLevel, setSelectedLevel] = useState<string>('all')
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
        fetchLogs()
        fetchStats()
      }, 3000) // Refresh every 3 seconds
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
  }, [autoRefresh, selectedCategory, selectedLevel])

  // Initial load
  useEffect(() => {
    fetchLogs()
    fetchStats()
  }, [selectedCategory, selectedLevel])

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
              fetchLogs()
              fetchStats()
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
    </div>
  )
}
