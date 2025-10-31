import React, { useEffect, useState } from 'react'
import FlipNumber from './FlipNumber'

interface RealtimePriceProps {
  symbol: string
  wsRef?: React.MutableRefObject<WebSocket | null>
  className?: string
}

export default function RealtimePrice({ symbol, wsRef, className = "" }: RealtimePriceProps) {
  const [price, setPrice] = useState<number | null>(null)
  const [priceChange, setPriceChange] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    // WebSocket listener for real-time price updates
    if (wsRef?.current) {
      const handleMessage = (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data)
          // Handle price updates from WebSocket
          if (message?.type === 'price_update' && message.symbol === symbol) {
            const newPrice = Number(message.price)
            if (!isNaN(newPrice)) {
              setPrice(prevPrice => {
                // Set price change direction for animation
                if (prevPrice !== null && prevPrice !== newPrice) {
                  setPriceChange(newPrice > prevPrice ? 'up' : newPrice < prevPrice ? 'down' : null)
                  // Clear the change indicator after animation
                  setTimeout(() => setPriceChange(null), 1000)
                }
                return newPrice
              })
            }
          }
        } catch {
          // Ignore non-JSON messages
        }
      }

      const ws = wsRef.current
      ws.addEventListener('message', handleMessage)

      return () => {
        ws.removeEventListener('message', handleMessage)
      }
    }
  }, [wsRef, symbol])

  useEffect(() => {
    // HTTP fallback for initial price fetch
    const fetchPrice = async () => {
      try {
        const response = await fetch(`/api/market/price/${symbol}`)
        if (response.ok) {
          const data = await response.json()
          const newPrice = data.price
          if (newPrice && !isNaN(newPrice)) {
            setPrice(prevPrice => {
              // Set price change direction for animation (only if no previous price)
              if (prevPrice === null) {
                return newPrice
              }
              if (prevPrice !== newPrice) {
                setPriceChange(newPrice > prevPrice ? 'up' : newPrice < prevPrice ? 'down' : null)
                // Clear the change indicator after animation
                setTimeout(() => setPriceChange(null), 1000)
              }
              return newPrice
            })
          }
        }
      } catch (error) {
        console.error(`Error fetching price for ${symbol}:`, error)
      }
    }

    // Only fetch initially if no WebSocket or as fallback
    fetchPrice()

    // Reduced frequency since WebSocket should handle real-time updates
    const interval = setInterval(fetchPrice, 5000) // 5 seconds fallback

    return () => clearInterval(interval)
  }, [symbol])

  if (price === null) {
    return (
      <div className={`text-xs text-muted-foreground ${className}`}>
        --
      </div>
    )
  }

  return (
    <div className={`flex items-center gap-1 ${className}`}>
      <FlipNumber
        value={price}
        prefix="$"
        decimals={2}
        className={`text-xs font-medium transition-colors duration-300 ${
          priceChange === 'up'
            ? 'text-green-500'
            : priceChange === 'down'
            ? 'text-red-500'
            : 'text-muted-foreground'
        }`}
      />
      {priceChange && (
        <span className={`text-xs transition-opacity duration-1000 ${
          priceChange === 'up' ? 'text-green-500' : 'text-red-500'
        }`}>
          {priceChange === 'up' ? '↗' : '↘'}
        </span>
      )}
    </div>
  )
}