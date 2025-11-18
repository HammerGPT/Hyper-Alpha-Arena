import React from 'react'
import { createPortal } from 'react-dom'
import { X, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ExchangeModalProps {
  isOpen: boolean
  onClose: () => void
}

const exchanges = [
  {
    id: 'hyperliquid',
    name: 'Hyperliquid',
    logo: '/static/hyperliquid_logo.png',
    status: 'active',
    description: 'Decentralized perpetual futures exchange',
    features: ['No KYC Required', 'Low Fees', 'High Performance'],
    buttonText: 'Open Futures',
    buttonVariant: 'default' as const,
    url: 'https://app.hyperliquid.xyz/trade'
  },
  {
    id: 'binance',
    name: 'Binance',
    logo: '/static/binance_logo.png',
    status: 'coming-soon',
    description: 'World\'s largest cryptocurrency exchange',
    features: ['30% Fee Discount', 'High Liquidity', 'Advanced Tools'],
    buttonText: 'Register First',
    buttonVariant: 'outline' as const,
    url: 'https://accounts.maxweb.red/register?ref=HYPERVIP'
  },
  {
    id: 'aster',
    name: 'Aster DEX',
    logo: '/static/aster_logo.png',
    status: 'coming-soon',
    description: 'Binance-compatible decentralized exchange',
    features: ['Lower Fees', 'Multi-chain Support', 'API Wallet Security'],
    buttonText: 'Register First',
    buttonVariant: 'outline' as const,
    url: 'https://www.asterdex.com/zh-CN/referral/2b5924'
  }
]

export default function ExchangeModal({ isOpen, onClose }: ExchangeModalProps) {
  if (!isOpen) return null

  const handleExchangeClick = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative bg-background border rounded-lg shadow-lg max-w-5xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div>
            <h2 className="text-2xl font-bold">Choose Exchange</h2>
            <p className="text-muted-foreground mt-1">Select an exchange to start trading</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Exchange Cards */}
        <div className="p-6">
          <div className="grid gap-6 md:grid-cols-3">
            {exchanges.map((exchange) => (
              <div
                key={exchange.id}
                className={`relative border rounded-lg p-8 transition-all hover:shadow-md ${
                  exchange.status === 'active'
                    ? 'border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20'
                    : 'border-gray-200 bg-gray-50/50 dark:border-gray-800 dark:bg-gray-950/20'
                }`}
              >
                {/* Status Badge */}
                {exchange.status === 'active' && (
                  <div className="absolute -top-2 -right-2 bg-green-500 text-white text-xs px-2 py-1 rounded-full font-medium">
                    Active
                  </div>
                )}
                {exchange.status === 'coming-soon' && (
                  <div className="absolute -top-2 -right-2 bg-orange-500 text-white text-xs px-2 py-1 rounded-full font-medium">
                    Coming Soon
                  </div>
                )}

                {/* Logo */}
                <div className="flex justify-center mb-4">
                  <img
                    src={exchange.logo}
                    alt={`${exchange.name} logo`}
                    className="w-16 h-16 rounded-full object-cover border-2 border-gray-200 dark:border-gray-700 aspect-square"
                  />
                </div>

                {/* Content */}
                <div className="text-center space-y-3">
                  <h3 className="text-lg font-semibold">{exchange.name}</h3>
                  <p className="text-sm text-muted-foreground">{exchange.description}</p>

                  {/* Features */}
                  <div className="space-y-1">
                    {exchange.features.map((feature, index) => (
                      <div key={index} className="text-xs text-muted-foreground flex items-center justify-center gap-1">
                        <div className="w-1 h-1 bg-current rounded-full" />
                        {feature}
                      </div>
                    ))}
                  </div>

                  {/* Button */}
                  <Button
                    variant={exchange.buttonVariant}
                    className="w-full mt-4 px-6 py-3 text-sm"
                    onClick={() => handleExchangeClick(exchange.url)}
                  >
                    {exchange.buttonText}
                    <ExternalLink className="ml-2 h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          {/* Footer Note */}
          <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <p className="text-sm text-blue-700 dark:text-blue-300 text-center">
              💡 <strong>Pro Tip:</strong> Register through our referral links to enjoy fee discounts and support the platform development.
            </p>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}