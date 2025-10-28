import React, { useEffect, useState } from 'react'
import { getCryptoSymbols, getPopularCryptos } from '../../lib/api'

interface CryptoSelectorProps {
  onSymbolSelect: (symbol: string, name: string) => void
  selectedSymbol?: string
}

interface CryptoInfo {
  symbol: string
  name: string
  price?: number
  market: string
}

export default function CryptoSelector({ onSymbolSelect, selectedSymbol }: CryptoSelectorProps) {
  const [popularCryptos, setPopularCryptos] = useState<CryptoInfo[]>([])
  const [allSymbols, setAllSymbols] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    loadCryptoData()
  }, [])

  const loadCryptoData = async () => {
    try {
      setLoading(true)
      
      // Load popular cryptos with prices
      const popular = await getPopularCryptos()
      setPopularCryptos(popular)

      // Load all available symbols
      const symbols = await getCryptoSymbols()
      setAllSymbols(symbols)
      
      setError(null)
    } catch (err) {
      console.error('Error loading crypto data:', err)
      setError('Failed to load crypto data')
    } finally {
      setLoading(false)
    }
  }

  const handleSymbolClick = (symbol: string) => {
    const name = symbol.split('/')[0] // Extract base currency (e.g., 'BTC' from 'BTC/USD')
    onSymbolSelect(symbol, name)
  }

  if (loading) {
    return (
      <div className="p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="text-red-600 mb-2">Error: {error}</div>
        <button 
          onClick={loadCryptoData}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Cryptocurrencies</h3>
        <button
          onClick={() => setShowAll(!showAll)}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          {showAll ? 'Show Popular' : 'Show All'}
        </button>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {showAll ? (
          // Show all symbols
          allSymbols.map((symbol) => (
            <div
              key={symbol}
              onClick={() => handleSymbolClick(symbol)}
              className={`p-3 border rounded cursor-pointer hover:bg-gray-50 ${
                selectedSymbol === symbol ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
              }`}
            >
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium">{symbol}</div>
                  <div className="text-xs text-gray-500">
                    {symbol.split('/')[0]} / {symbol.split('/')[1]}
                  </div>
                </div>
              </div>
            </div>
          ))
        ) : (
          // Show popular cryptos with prices
          popularCryptos.map((crypto) => (
            <div
              key={crypto.symbol}
              onClick={() => handleSymbolClick(crypto.symbol)}
              className={`p-3 border rounded cursor-pointer hover:bg-gray-50 ${
                selectedSymbol === crypto.symbol ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
              }`}
            >
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium">{crypto.symbol}</div>
                  <div className="text-xs text-gray-500">{crypto.name}</div>
                </div>
                {crypto.price && (
                  <div className="text-right">
                    <div className="font-medium">${crypto.price.toLocaleString()}</div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {!showAll && popularCryptos.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No popular cryptocurrencies available
        </div>
      )}
    </div>
  )
}