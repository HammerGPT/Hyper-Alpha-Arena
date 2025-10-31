import React, { useEffect, useState } from 'react'
import FlipNumber from '../portfolio/FlipNumber'

interface PriceTickerProps {
  symbol: string
  name: string
}

export default function PriceTicker({ symbol, name }: PriceTickerProps) {
  const [price, setPrice] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchPrice = async () => {
      try {
        const response = await fetch(`/api/market-data/price/${symbol}`)
        if (response.ok) {
          const data = await response.json()
          setPrice(data.price)
        }
      } catch (error) {
        console.error(`Error fetching price for ${symbol}:`, error)
      } finally {
        setLoading(false)
      }
    }

    fetchPrice()
    const interval = setInterval(fetchPrice, 1500) // 1.5 seconds

    return () => clearInterval(interval)
  }, [symbol])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-md bg-muted/70 px-3 py-2 shadow-sm border border-border/70 w-[140px]">
        <div className="flex flex-col leading-tight">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {symbol.split('/')[0]}
          </span>
          <div className="text-sm font-semibold text-muted-foreground">--</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 rounded-md bg-muted/70 px-3 py-2 shadow-sm border border-border/70 w-[140px]">
      <div className="flex flex-col leading-tight">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {symbol.split('/')[0]}
        </span>
        {price !== null ? (
          <FlipNumber
            value={price}
            prefix="$"
            decimals={2}
            className="text-sm font-semibold text-primary"
          />
        ) : (
          <div className="text-sm font-semibold text-muted-foreground">--</div>
        )}
      </div>
    </div>
  )
}