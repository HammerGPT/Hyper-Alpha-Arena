import { useEffect, useState } from 'react'
import { toast } from 'react-hot-toast'
import OrderForm from './OrderForm'
import AuthDialog from './AuthDialog'
import TradeButtons from './TradeButtons'

interface User {
  id?: string
  current_cash: number
  frozen_cash: number
  has_password: boolean
}

interface PositionLite { symbol: string; market: string; available_quantity: number }

interface TradingPanelProps {
  onPlace: (payload: any) => void
  user?: User
  positions?: PositionLite[]
  lastPrices?: Record<string, number | null>
}

export default function TradingPanel({ onPlace, user, positions = [], lastPrices = {} }: TradingPanelProps) {
  const [symbol, setSymbol] = useState('BTC')
  const [market] = useState<'US'>('US')
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('LIMIT')
  const [price, setPrice] = useState<number>(190)
  const [quantity, setQuantity] = useState<number>(2)
  const [showPasswordDialog, setShowPasswordDialog] = useState<boolean>(false)
  const [pendingTrade, setPendingTrade] = useState<{side: 'BUY' | 'SELL'} | null>(null)
  const [authSessionToken, setAuthSessionToken] = useState<string>('')
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false)

  // When switching to MARKET, price refreshes with latest quote from WS/parent component
  const onSelectOrderType = (v: 'MARKET' | 'LIMIT') => {
    setOrderType(v)
    if (v === 'MARKET') {
      const lp = lastPrices[`${symbol}.${market}`]
      if (lp && Number.isFinite(lp)) {
        setPrice(Math.round(lp * 100) / 100)
      }
      toast('Using market price from server', { icon: '💹' })
    }
  }

  // In market mode, display price automatically refreshes with latest price pushed via WS
  useEffect(() => {
    if (orderType !== 'MARKET') return
    const lp = lastPrices[`${symbol}.${market}`]
    if (lp && Number.isFinite(lp)) {
      setPrice(Math.round(lp * 100) / 100)
    }
  }, [orderType, lastPrices, symbol, market])

  const adjustPrice = (delta: number) => {
    if (orderType === 'MARKET') return // Market orders don't allow manual price changes
    const newPrice = Math.max(0, price + delta)
    setPrice(Math.round(newPrice * 100) / 100) // Ensure 2 decimal places
  }

  const adjustQuantity = (delta: number) => {
    setQuantity(Math.max(0, quantity + delta))
  }

  // Check if user has valid auth session on component mount
  useEffect(() => {
    const savedToken = localStorage.getItem(`auth_session_${user?.id}`)
    const savedExpiry = localStorage.getItem(`auth_expiry_${user?.id}`)
    
    if (savedToken && savedExpiry && user?.id) {
      const expiryDate = new Date(savedExpiry)
      if (expiryDate > new Date()) {
        // Verify token with backend
        verifyAuthSession(savedToken)
      } else {
        // Token expired, clear storage
        clearAuthSession()
      }
    }
  }, [user?.id])

  const verifyAuthSession = async (token: string) => {
    try {
      const response = await fetch('/api/account/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_token: token })
      })
      const data = await response.json()
      
      if (data.valid && data.user_id === user?.id) {
        setAuthSessionToken(token)
        setIsAuthenticated(true)
      } else {
        clearAuthSession()
      }
    } catch (error) {
      console.error('Failed to verify auth session:', error)
      clearAuthSession()
    }
  }

  const clearAuthSession = () => {
    setAuthSessionToken('')
    setIsAuthenticated(false)
    if (user?.id) {
      localStorage.removeItem(`auth_session_${user.id}`)
      localStorage.removeItem(`auth_expiry_${user.id}`)
    }
  }

  const handleAuthenticate = (sessionToken: string, orderData: any) => {
    setAuthSessionToken(sessionToken)
        setIsAuthenticated(true)
    onPlace(orderData)
  }

  const handleCloseAuthDialog = () => {
      setShowPasswordDialog(false)
      setPendingTrade(null)
  }

  const handleBuy = () => {
    if (orderType === 'LIMIT' && price <= 0) {
      toast.error('Please input a valid limit price')
      return
    }
    if (quantity <= 0 || !Number.isFinite(quantity)) {
      toast.error('Please input a valid quantity')
      return
    }
    const amount = price * quantity
    const cashAvailable = user?.current_cash ?? 0
    if (amount > cashAvailable) {
      toast.error('Insufficient available cash')
      return
    }
    
    // If already authenticated, trade directly
    if (isAuthenticated && authSessionToken) {
      const orderData: any = {
        symbol,
        name,
        market,
        side: 'BUY',
        order_type: orderType,
        price: orderType === 'LIMIT' ? price : undefined,
        quantity,
        session_token: authSessionToken
      }
      onPlace(orderData)
    } else {
      // Not authenticated, show password dialog
      setPendingTrade({side: 'BUY'})
      setShowPasswordDialog(true)
    }
  }

  const handleSell = () => {
    if (orderType === 'LIMIT' && price <= 0) {
      toast.error('Please input a valid limit price')
      return
    }
    if (quantity <= 0 || !Number.isFinite(quantity)) {
      toast.error('Please input a valid quantity')
      return
    }
    const positionAvailable = positions.find(p => p.symbol === symbol && p.market === market)?.available_quantity || 0
    if (quantity > positionAvailable) {
      toast.error('Insufficient sellable position')
      return
    }
    
    // If already authenticated, trade directly
    if (isAuthenticated && authSessionToken) {
      const orderData: any = {
        symbol,
        name,
        market,
        side: 'SELL',
        order_type: orderType,
        price: orderType === 'LIMIT' ? price : undefined,
        quantity,
        session_token: authSessionToken
      }
      onPlace(orderData)
    } else {
      // Not authenticated, show password dialog
      setPendingTrade({side: 'SELL'})
      setShowPasswordDialog(true)
    }
  }

  return (
    <div className="space-y-4 w-[320px] flex-shrink-0">
      <OrderForm
        symbol={symbol}
        orderType={orderType}
        price={price}
        quantity={quantity}
        onSymbolChange={setSymbol}
        onOrderTypeChange={onSelectOrderType}
        onPriceChange={setPrice}
        onQuantityChange={setQuantity}
        onAdjustPrice={adjustPrice}
        onAdjustQuantity={adjustQuantity}
        lastPrices={lastPrices}
      />

      <TradeButtons
        symbol={symbol}
        market={market}
        orderType={orderType}
        price={price}
        quantity={quantity}
        user={user}
        positions={positions}
        lastPrices={lastPrices}
        onBuy={handleBuy}
        onSell={handleSell}
      />

      <AuthDialog
        isOpen={showPasswordDialog}
        pendingTrade={pendingTrade}
        user={user}
        onClose={handleCloseAuthDialog}
        onAuthenticate={handleAuthenticate}
        orderData={{
          symbol,
          market,
          side: pendingTrade?.side || 'BUY',
          order_type: orderType,
          price: orderType === 'LIMIT' ? price : undefined,
          quantity
        }}
      />
    </div>
  )
}