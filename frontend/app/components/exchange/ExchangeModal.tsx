import React, { useState } from 'react'
import { createPortal } from 'react-dom'
import { X, ExternalLink, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useExchange } from '@/contexts/ExchangeContext'
import { ExchangeId } from '@/lib/types/exchange'

interface ExchangeModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function ExchangeModal({ isOpen, onClose }: ExchangeModalProps) {
  const { exchanges, currentExchange, selectExchange, isLoading } = useExchange()
  const [selectedExchange, setSelectedExchange] = useState<ExchangeId>(currentExchange)
  const [hasChanges, setHasChanges] = useState(false)

  // Reset state when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setSelectedExchange(currentExchange)
      setHasChanges(false)
    }
  }, [isOpen, currentExchange])

  if (!isOpen) return null

  const handleExchangeClick = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const handleRadioChange = (exchangeId: ExchangeId) => {
    const exchange = exchanges.find(ex => ex.id === exchangeId)
    if (exchange?.selectable) {
      setSelectedExchange(exchangeId)
      setHasChanges(exchangeId !== currentExchange)
    }
  }

  const handleSave = async () => {
    if (hasChanges && selectedExchange !== currentExchange) {
      await selectExchange(selectedExchange)
      setHasChanges(false)
      onClose()
    }
  }

  const handleCancel = () => {
    setSelectedExchange(currentExchange)
    setHasChanges(false)
    onClose()
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
            onClick={handleCancel}
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
                className={`relative border-2 rounded-lg p-8 transition-all duration-200 ${
                  selectedExchange === exchange.id
                    ? 'border-green-500 bg-green-50/50 dark:border-green-600 dark:bg-green-950/30 shadow-lg'
                    : exchange.selectable
                    ? 'border-gray-200 bg-gray-50/50 dark:border-gray-700 dark:bg-gray-950/20 cursor-pointer hover:border-green-300 hover:shadow-md'
                    : 'border-gray-200 bg-gray-50/50 dark:border-gray-800 dark:bg-gray-950/20 opacity-60'
                }`}
                onClick={() => exchange.selectable && handleRadioChange(exchange.id)}
              >
                {/* Radio Button - Moved to center top */}
                <div className="flex justify-center mb-4">
                  <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all duration-200 ${
                    selectedExchange === exchange.id
                      ? 'border-green-500 bg-green-500 shadow-md'
                      : exchange.selectable
                      ? 'border-gray-400 hover:border-green-400 hover:shadow-sm'
                      : 'border-gray-300'
                  }`}>
                    {selectedExchange === exchange.id && (
                      <Check className="w-4 h-4 text-white font-bold" />
                    )}
                  </div>
                </div>

                {/* Status Badge */}
                {selectedExchange === exchange.id && exchange.id === currentExchange && (
                  <div className="absolute -top-2 -right-2 bg-green-500 text-white text-xs px-2 py-1 rounded-full font-medium">
                    Active
                  </div>
                )}
                {exchange.comingSoon && (
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
                    onClick={(e) => {
                      e.stopPropagation()
                      handleExchangeClick(exchange.referralLink)
                    }}
                  >
                    {exchange.buttonText}
                    <ExternalLink className="ml-2 h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          {/* Bottom Action Bar */}
          {hasChanges && (
            <div className="mt-6 p-4 bg-yellow-50 dark:bg-yellow-950/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-sm text-yellow-700 dark:text-yellow-300 font-medium">
                    Exchange Selection Changed
                  </p>
                  <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                    Data collection and trading will switch to {exchanges.find(ex => ex.id === selectedExchange)?.displayName}
                  </p>
                </div>
                <div className="flex gap-3 ml-4">
                  <Button
                    variant="outline"
                    onClick={handleCancel}
                    disabled={isLoading}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleSave}
                    disabled={isLoading}
                  >
                    {isLoading ? 'Saving...' : 'Save Changes'}
                  </Button>
                </div>
              </div>
            </div>
          )}

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