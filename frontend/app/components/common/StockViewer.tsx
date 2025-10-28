import React, { useState, useEffect, useRef, useMemo } from 'react'
import { RefreshCw } from 'lucide-react'

declare global {
  interface Window {
    TradingView?: {
      widget: new (config: Record<string, unknown>) => unknown
    }
    __tradingViewScriptLoading?: boolean
  }
}

interface cryptoInfo {
  item: string
  value: string
}

interface cryptoViewerProps {
  symbol: string | null
  title?: string
  subtitle?: string
  className?: string
}

export default function cryptoViewer({ symbol, title, subtitle, className = "" }: cryptoViewerProps) {
  const [cryptoInfo, setcryptoInfo] = useState<cryptoInfo[]>([])
  const [cryptoInfoLoading, setcryptoInfoLoading] = useState(false)
  const [cryptoInfoError, setcryptoInfoError] = useState<string | null>(null)
  const chartContainerRef = useRef<HTMLDivElement | null>(null)
  const tradingViewContainerId = useMemo(
    () => `tradingview-widget-${Math.random().toString(36).slice(2)}`,
    []
  )

  const fetchcryptoInfo = async (symbol: string) => {
    if (!symbol) return

    setcryptoInfoLoading(true)
    setcryptoInfoError(null)

    try {
      const response = await fetch(`/api/ranking/crypto-info/${symbol}`)
      const data = await response.json()
      
      if (data.success) {
        setcryptoInfo(data.data || [])
      } else {
        setcryptoInfoError(data.error || 'Failed to fetch crypto info')
        setcryptoInfo([])
      }
    } catch (err) {
      setcryptoInfoError('Failed to connect to server')
      setcryptoInfo([])
      console.error('Error fetching crypto info:', err)
    } finally {
      setcryptoInfoLoading(false)
    }
  }

  useEffect(() => {
    if (symbol && symbol !== 'IXIC') {
      fetchcryptoInfo(symbol)
    } else {
      setcryptoInfo([])
      setcryptoInfoError(null)
    }
  }, [symbol])

  useTradingViewChart(chartContainerRef, tradingViewContainerId, symbol)

  return (
    <div className={className}>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-medium">
          {title || (symbol ? `${symbol} - crypto Chart` : 'Select a crypto')}
        </h2>
        {subtitle && <div className="text-xs text-muted-foreground">{subtitle}</div>}
      </div>
      
      <div className="relative w-full h-[50vh] mb-4">
        <div
          ref={chartContainerRef}
          id={tradingViewContainerId}
          className="h-full w-full"
        />
      </div>

      {/* crypto Info Section */}
      <div className="border-t pt-4">
        {cryptoInfoLoading && (
          <div className="flex items-center justify-center py-4">
            <RefreshCw className="w-4 h-4 animate-spin mr-2" />
            <span className="text-xs">Loading crypto info...</span>
          </div>
        )}

        {cryptoInfoError && (
          <div className="text-red-700 text-xs">
            {cryptoInfoError}
          </div>
        )}

        {!cryptoInfoLoading && !cryptoInfoError && cryptoInfo.length > 0 && (
          <div className="max-h-[28vh] overflow-y-auto">
            <div className="grid grid-cols-1 gap-1 text-xs">
              {cryptoInfo.map((info, index) => (
                <div key={index} className="flex justify-between py-1 border-b border-gray-500 last:border-b-0">
                  <span className="font-medium text-gray-600 truncate mr-2">{info.item}:</span>
                  <span className="text-left">{info.value || '-'}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {!cryptoInfoLoading && !cryptoInfoError && cryptoInfo.length === 0 && symbol && symbol !== 'IXIC' && (
          <div className="text-center py-4 text-gray-500 text-xs">
            No information available for {symbol}
          </div>
        )}

        {(!symbol || symbol === 'IXIC') && (
          <div className="text-center py-4 text-gray-500 text-xs">
            Select a crypto to view information
          </div>
        )}
      </div>
    </div>
  )
}

function useTradingViewChart(
  containerRef: React.RefObject<HTMLDivElement | null>,
  containerId: string,
  symbol: string | null
) {
  const [theme, setTheme] = useState<'light' | 'dark'>('dark')

  useEffect(() => {
    if (typeof document === 'undefined') {
      setTheme('dark')
      return
    }

    const updateTheme = () => {
      setTheme(document.documentElement.classList.contains('dark') ? 'dark' : 'light')
    }

    updateTheme()

    const observer = new MutationObserver(updateTheme)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class']
    })

    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    if (!symbol) {
      clearContainerChildren(container)
      return
    }

    const normalizedSymbol = normalizeSymbol(symbol)
    const widgetContainerId = containerId
    container.id = widgetContainerId
    clearContainerChildren(container)

    let widgetScript: HTMLScriptElement | null = null
    let pollTimer: number | null = null
    const initializeWidget = () => {
      const TradingView = window.TradingView
      if (!TradingView || typeof TradingView.widget !== 'function') {
        console.error('TradingView widget unavailable')
        return
      }

      new TradingView.widget({
        autosize: true,
        symbol: normalizedSymbol,
        interval: 'D',
        timezone: 'America/New_York',
        theme,
        style: '1',
        locale: 'en',
        toolbar_bg: '#f1f3f6',
        hide_legend: false,
        hide_top_toolbar: false,
        allow_symbol_change: false,
        withdateranges: true,
        container_id: widgetContainerId,
        studies: [
          {
            "id": "MASimple@tv-basicstudies",
            "inputs": {
              "length": 5
            }
          },
          {
            "id": "MASimple@tv-basicstudies",
            "inputs": {
              "length": 20
            }
          }
        ]
      })
    }

    if (window.TradingView && typeof window.TradingView.widget === 'function') {
      initializeWidget()
    } else if (!window.__tradingViewScriptLoading) {
      window.__tradingViewScriptLoading = true
      widgetScript = document.createElement('script')
      widgetScript.src = 'https://s3.tradingview.com/tv.js'
      widgetScript.async = true
      widgetScript.onload = () => {
        window.__tradingViewScriptLoading = false
        initializeWidget()
      }
      widgetScript.onerror = () => console.error('Failed to load TradingView script')
      document.body.appendChild(widgetScript)
    } else {
      pollTimer = window.setInterval(() => {
        if (window.TradingView && typeof window.TradingView.widget === 'function') {
          window.clearInterval(pollTimer as number)
          initializeWidget()
        }
      }, 100)
    }

    return () => {
      if (widgetScript) {
        widgetScript.onload = null
      }
      if (pollTimer !== null) {
        window.clearInterval(pollTimer)
      }
      clearContainerChildren(container)
    }
  }, [containerRef, containerId, symbol, theme])
}

function normalizeSymbol(symbol: string): string {
  return symbol.replace(/\.US$/i, '').trim().toUpperCase()
}

function clearContainerChildren(container: HTMLElement) {
  while (container.firstChild) {
    container.removeChild(container.firstChild)
  }
}
