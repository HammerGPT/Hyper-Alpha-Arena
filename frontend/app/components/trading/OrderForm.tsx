import React, { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { getCryptoSymbols, getPopularCryptos } from '../../lib/api'

interface CryptoInfo {
  symbol: string
  name: string
  price?: number
  market: string
}

interface OrderFormProps {
  symbol: string
  orderType: 'MARKET' | 'LIMIT'
  price: number
  quantity: number
  onSymbolChange: (symbol: string) => void
  onOrderTypeChange: (orderType: 'MARKET' | 'LIMIT') => void
  onPriceChange: (price: number) => void
  onQuantityChange: (quantity: number) => void
  onAdjustPrice: (delta: number) => void
  onAdjustQuantity: (delta: number) => void
  lastPrices?: Record<string, number | null>
}

export default function OrderForm({
  symbol,
  orderType,
  price,
  quantity,
  onSymbolChange,
  onOrderTypeChange,
  onPriceChange,
  onQuantityChange,
  onAdjustPrice,
  onAdjustQuantity,
  lastPrices = {}
}: OrderFormProps) {
  const [allSymbols, setAllSymbols] = useState<string[]>([])
  const [popularCryptos, setPopularCryptos] = useState<CryptoInfo[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)
  const [loading, setLoading] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Load crypto data on component mount
  useEffect(() => {
    loadCryptoData()
  }, [])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const loadCryptoData = async () => {
    try {
      setLoading(true)
      const [symbols, popular] = await Promise.all([
        getCryptoSymbols(),
        getPopularCryptos()
      ])
      setAllSymbols(symbols)
      setPopularCryptos(popular)
    } catch (error) {
      console.error('Error loading crypto data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handlePriceChange = (value: string) => {
    if (orderType === 'MARKET') return // 市价单不允许手动改价
    // 只允许数字和一个小数点
    if (!/^\d*\.?\d{0,2}$/.test(value)) return
    
    const numValue = parseFloat(value) || 0
    onPriceChange(numValue)
  }

  const handleSymbolSelect = (selectedSymbol: string) => {
    onSymbolChange(selectedSymbol)
    setSearchTerm('')
    setShowDropdown(false)
  }

  const handleSearchChange = (value: string) => {
    setSearchTerm(value)
    setShowDropdown(true)
    // If user types a symbol directly, update it
    if (value && allSymbols.includes(value.toUpperCase())) {
      onSymbolChange(value.toUpperCase())
    }
  }

  // Filter symbols based on search term
  const filteredSymbols = searchTerm
    ? allSymbols.filter(s => 
        s.toLowerCase().includes(searchTerm.toLowerCase())
      ).slice(0, 10) // Limit to 10 results
    : popularCryptos.map(c => c.symbol).slice(0, 6) // Show top 6 popular when no search

  return (
    <div className="space-y-4">
      {/* Symbol */}
      <div className="space-y-2">
        <label className="text-xs">Code</label>
        <div className="relative" ref={dropdownRef}>
          <Input 
            value={searchTerm || symbol}
            onChange={(e) => handleSearchChange(e.target.value)}
            onFocus={() => setShowDropdown(true)}
            placeholder="Search crypto symbols..."
          />
          
          {/* Dropdown */}
          {showDropdown && (
            <div className="absolute top-full left-0 right-0 z-50 bg-white border border-gray-200 rounded-md shadow-lg max-h-64 overflow-y-auto mt-1">
              {loading ? (
                <div className="p-3 text-center text-gray-500">Loading...</div>
              ) : filteredSymbols.length > 0 ? (
                <>
                  {!searchTerm && (
                    <div className="px-3 py-2 text-xs text-gray-500 bg-gray-50 border-b">
                      Popular Cryptocurrencies
                    </div>
                  )}
                  {filteredSymbols.map((symbolItem) => {
                    const crypto = popularCryptos.find(c => c.symbol === symbolItem)
                    return (
                      <div
                        key={symbolItem}
                        onClick={() => handleSymbolSelect(symbolItem)}
                        className="px-3 py-2 hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0"
                      >
                        <div className="flex justify-between items-center">
                          <div>
                            <div className="text-xs font-medium">{symbolItem}</div>
                            {crypto && (
                              <div className="text-xs text-gray-500">{crypto.name}</div>
                            )}
                          </div>
                          {crypto?.price && (
                            <div className="text-xs text-gray-600">
                              ${crypto.price.toLocaleString()}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </>
              ) : (
                <div className="p-3 text-center text-gray-500">
                  {searchTerm ? 'No symbols found' : 'No data available'}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 订单类型 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <label className="text-xs text-muted-foreground">Order Type</label>
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-info w-3 h-3 text-muted-foreground">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M12 16v-4"></path>
            <path d="M12 8h.01"></path>
          </svg>
        </div>
        <Select value={orderType} onValueChange={(v) => onOrderTypeChange(v as 'MARKET' | 'LIMIT')}>
          <SelectTrigger className="bg-input text-xs h-6">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="LIMIT">Limit Order</SelectItem>
            <SelectItem value="MARKET">Market Order</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* 价格 */}
      <div className="space-y-2">
        <label className="text-xs">Price</label>
        <div className="flex items-center gap-2">
         <Button 
            onClick={() => onAdjustPrice(-0.01)}
            variant="outline"
            disabled={orderType === 'MARKET'}
          >
            -
          </Button>
          <div className="relative flex-1">
           <Input 
              inputMode="decimal"
              value={price.toString()}
              onChange={(e) => handlePriceChange(e.target.value)}
              className="text-center"
              disabled={orderType === 'MARKET'}
            />
          </div>
         <Button 
            onClick={() => onAdjustPrice(0.01)}
            variant="outline"
            disabled={orderType === 'MARKET'}
          >
            +
          </Button>
        </div>
      </div>

      {/* 数量 */}
      <div className="space-y-2">
        <label className="text-xs">Quantity</label>
        <div className="flex items-center gap-2">
          <Button 
            onClick={() => onAdjustQuantity(-1)}
            variant="outline"
          >
            -
          </Button>
          <div className="relative flex-1">
            <Input 
              inputMode="numeric"
              value={quantity}
              onChange={(e) => onQuantityChange(parseInt(e.target.value) || 0)}
              className="text-center"
            />
          </div>
          <Button 
            onClick={() => onAdjustQuantity(1)}
            variant="outline"
          >
            +
          </Button>
        </div>
      </div>
    </div>
  )
}
