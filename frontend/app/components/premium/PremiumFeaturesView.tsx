'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Database,
  TrendingUp,
  Clock,
  Target,
  Lock,
  ExternalLink,
  Info
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useAuth } from '@/contexts/AuthContext'

interface PremiumFeaturesViewProps {
  onAccountUpdated?: () => void
}

export default function PremiumFeaturesView({ onAccountUpdated }: PremiumFeaturesViewProps) {
  const { membership, membershipLoading } = useAuth()

  const [isLoading, setIsLoading] = useState(true)
  const [samplingDepth, setSamplingDepth] = useState(10)
  const [samplingInterval, setSamplingInterval] = useState(18)
  const [advancedIndicators, setAdvancedIndicators] = useState({
    momentum: false,
    rsi: false,
    macd: false,
    bollinger: false
  })
  const [multiTimeframe, setMultiTimeframe] = useState({
    enabled: false,
    timeframes: [] as string[]
  })

  // Determine if user has premium subscription
  const isPremium = membership?.status === 'ACTIVE'
  const maxAllowedDepth = isPremium ? 60 : 10
  const subscriptionEndDate = membership?.currentPeriodEnd

  useEffect(() => {
    fetchGlobalConfig()
  }, [])

  const fetchGlobalConfig = async () => {
    try {
      setIsLoading(true)

      // Fetch global sampling configuration
      const response = await fetch('/api/config/global-sampling')
      if (!response.ok) {
        throw new Error('Failed to fetch global sampling configuration')
      }
      const data = await response.json()

      setSamplingDepth(data.sampling_depth || 10)
      setSamplingInterval(data.sampling_interval || 18)

      console.log('Global config loaded:', data)
    } catch (error) {
      console.error('Failed to fetch global config:', error)
      toast.error('Failed to load sampling configuration')
    } finally {
      setIsLoading(false)
    }
  }

  const handleUpgradeClick = () => {
    window.open('https://www.akooi.com/#pricing-section', '_blank')
  }

  const handleSaveConfiguration = async (section: string) => {
    if (section === 'sampling-pool') {
      // Check premium requirement
      if (samplingDepth > 10 && !isPremium) {
        toast.error('Premium subscription required for sampling depth > 10')
        handleUpgradeClick()
        return
      }

      try {
        const response = await fetch(`/api/config/global-sampling`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            sampling_depth: samplingDepth
          })
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || 'Failed to save configuration')
        }

        const result = await response.json()
        toast.success('Sampling depth configuration saved successfully!')

        // Refresh configuration
        await fetchGlobalConfig()
      } catch (error) {
        console.error('Failed to save sampling configuration:', error)
        toast.error(error instanceof Error ? error.message : 'Failed to save configuration')
      }
    } else {
      // For not-yet-implemented features
      toast('This feature is coming soon!', { icon: '🚧' })
    }
  }

  if (isLoading || membershipLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-muted-foreground">Loading premium features...</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header Section */}
      <div className="px-6 py-4 border-b min-h-[110px]">
        <div className="space-y-2">
          {/* Title row with subscription card */}
          <div className="flex items-stretch gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold">Premium Features</h1>
                {isPremium && subscriptionEndDate && (
                  <Badge variant="outline" className="text-sm">
                    Active until {new Date(subscriptionEndDate).toLocaleDateString()}
                  </Badge>
                )}
              </div>
              <p className="text-muted-foreground">
                Continuous development requires financial support. Subscribe to unlock:
              </p>
              <div className="flex flex-wrap gap-3 text-sm">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Target className="w-4 h-4" />
                  <span>Advanced data analysis</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Clock className="w-4 h-4" />
                  <span>Priority technical support</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <TrendingUp className="w-4 h-4" />
                  <span>Feature request priority</span>
                </div>
              </div>
            </div>

            {/* Subscribe card next to title */}
            {!isPremium && (
              <Card className="border text-card-foreground shadow border-orange-500/50 bg-orange-50/5 h-[100px] flex">
                <CardContent className="p-4 flex flex-col justify-center h-full space-y-3">
                  <div className="space-y-1">
                    <p className="font-medium text-sm">Premium subscription required</p>
                    <p className="text-xs text-muted-foreground">
                      Unlock all features below with a premium subscription
                    </p>
                  </div>
                  <Button
                    onClick={handleUpgradeClick}
                    className="gap-2 shrink-0 h-8 text-xs self-start w-full"
                  >
                    Subscribe Now
                    <ExternalLink className="w-4 h-4" />
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>

      {/* Features Container with scroll */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="space-y-8">
          {/* Data Collection Section */}
          <section className="space-y-4">
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-primary" />
              <h2 className="text-xl font-semibold">Data Collection</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <Card>
                <CardHeader className="pb-3">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2 text-lg">
                      60+ Sampling Pool Depth
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Provide AI with deeper historical data for better trend analysis
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium">Sampling Depth (points)</span>
                      <span className="text-xs text-muted-foreground">{samplingDepth} points</span>
                    </div>
                    <div className="flex gap-2">
                      {[10, 20, 30, 40, 50, 60].map((depth) => (
                        <Button
                          key={depth}
                          variant={samplingDepth === depth ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => setSamplingDepth(depth)}
                          disabled={depth > maxAllowedDepth}
                          className="flex-1 h-7 text-xs"
                        >
                          {depth}
                        </Button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1 p-3 bg-muted/50 rounded-lg text-xs">
                    <div className="font-medium flex items-center gap-2">
                      <Info className="w-3 h-3" />
                      Current Configuration
                    </div>
                    <div className="space-y-0.5 text-muted-foreground ml-5">
                      <div>• Sampling Interval: {samplingInterval} seconds</div>
                      <div>• Data Coverage: {((samplingDepth * samplingInterval) / 60).toFixed(1)} minutes of price history</div>
                      <div>• Storage: Minimal (rolling buffer)</div>
                      <div>• Estimated Accuracy Boost: +{Math.round(Math.max(0, (samplingDepth - 10) / 5))}%</div>
                    </div>
                  </div>

                  <Button
                    onClick={() => handleSaveConfiguration('sampling-pool')}
                    className="w-full h-8 text-xs"
                  >
                    Save Configuration
                  </Button>
                </CardContent>
              </Card>
            </div>
          </section>

          {/* Analysis Tools Section */}
          <section className="space-y-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-primary" />
              <h2 className="text-xl font-semibold">Analysis Tools</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {/* Advanced Indicators */}
              <Card className="opacity-60">
                <CardHeader className="pb-3">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2 text-lg">
                      Advanced Indicators Package
                      <Badge variant="outline" className="text-xs">Coming Soon</Badge>
                    </CardTitle>
                    <CardDescription className="text-xs">
                      7 advanced technical indicators for deeper market analysis
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-2">
                    {Object.entries(advancedIndicators).map(([key]) => (
                      <div key={key} className="flex items-center justify-between p-2 border rounded-lg opacity-50">
                        <div className="flex-1">
                          <div className="text-xs font-medium capitalize">
                            {key === 'rsi' ? 'RSI' : key === 'macd' ? 'MACD' : key === 'bollinger' ? 'Bollinger Bands' : key}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {key === 'momentum' && 'Momentum oscillator for trend strength'}
                            {key === 'rsi' && 'Relative Strength Index for overbought/oversold'}
                            {key === 'macd' && 'Moving Average Convergence Divergence'}
                            {key === 'bollinger' && 'Volatility bands for price extremes'}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <Button
                    disabled
                    className="w-full h-8 text-xs"
                  >
                    Coming Soon
                  </Button>
                </CardContent>
              </Card>

              {/* Multi-Timeframe Analysis */}
              <Card className="opacity-60">
                <CardHeader className="pb-3">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2 text-lg">
                      Multi-Timeframe Analysis
                      <Badge variant="outline" className="text-xs">Coming Soon</Badge>
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Simultaneous monitoring of 6 timeframes from 1-minute to daily
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg opacity-50">
                    <div className="flex-1">
                      <div className="text-xs font-medium">
                        Enable Multi-Timeframe Analysis
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Available timeframes: 1m, 5m, 15m, 1h, 4h, 1d
                      </p>
                    </div>
                  </div>

                  <Button
                    disabled
                    className="w-full h-8 text-xs"
                  >
                    Coming Soon
                  </Button>
                </CardContent>
              </Card>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
