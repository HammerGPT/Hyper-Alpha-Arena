import React from 'react'
import { Button } from '@/components/ui/button'
import { toast } from 'react-hot-toast'

interface User {
  current_cash: number
  frozen_cash: number
  has_password: boolean
  id?: string
}

interface AuthDialogProps {
  isOpen: boolean
  pendingTrade: { side: 'BUY' | 'SELL' } | null
  user?: User
  onClose: () => void
  onAuthenticate: (sessionToken: string, orderData: any) => void
  orderData: {
    symbol: string
    market: string
    side: 'BUY' | 'SELL'
    order_type: 'MARKET' | 'LIMIT'
    price?: number
    quantity: number
  }
}

export default function AuthDialog({
  isOpen,
  pendingTrade,
  user,
  onClose,
  onAuthenticate,
  orderData
}: AuthDialogProps) {

  const handleConfirmTrade = () => {
    if (!pendingTrade) return
    
    // For paper trading, just confirm the trade without authentication
    toast.success('Trade confirmed - Paper Trading Mode')
    
    // Use a dummy session token for paper trading
    const dummySessionToken = 'paper-trading-session'
    const finalOrderData = {
      ...orderData,
      session_token: dummySessionToken
    }

    onAuthenticate(dummySessionToken, finalOrderData)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg p-6 w-80 max-w-sm mx-4">
        <h3 className="text-lg font-semibold mb-4">
          Confirm Trade - {pendingTrade?.side === 'BUY' ? 'Buy' : 'Sell'}
        </h3>
        
        <div className="space-y-4">
          <div className="text-xs text-muted-foreground">
            <p><strong>Symbol:</strong> {orderData.symbol}</p>
            <p><strong>Type:</strong> {orderData.order_type}</p>
            <p><strong>Quantity:</strong> {orderData.quantity}</p>
            {orderData.price && <p><strong>Price:</strong> ${orderData.price}</p>}
          </div>

          <div className="bg-blue-50 dark:bg-blue-950 p-3 rounded">
            <p className="text-xs text-blue-700 dark:text-blue-300">
              📄 Paper Trading Mode - No real money involved
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              onClick={onClose}
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirmTrade}
              className="flex-1"
            >
              Confirm Trade
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
