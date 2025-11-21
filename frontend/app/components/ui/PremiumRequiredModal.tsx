import React from 'react'
import { createPortal } from 'react-dom'
import { X, ExternalLink, Crown, Sparkles, Zap, Shield } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PremiumRequiredModalProps {
  isOpen: boolean
  onClose: () => void
  onSubscribe: () => void
  featureName?: string
  description?: string
}

const premiumBenefits = [
  {
    icon: Sparkles,
    title: 'Advanced Data Analysis',
    description: 'Deeper historical data for better trend analysis'
  },
  {
    icon: Zap,
    title: 'Priority Support',
    description: 'Get faster responses from our technical team'
  },
  {
    icon: Shield,
    title: 'Feature Priority',
    description: 'Your feature requests get prioritized'
  }
]

export default function PremiumRequiredModal({
  isOpen,
  onClose,
  onSubscribe,
  featureName = 'This feature',
  description
}: PremiumRequiredModalProps) {
  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-background border rounded-lg shadow-lg max-w-md w-full mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-orange-400 to-orange-600 flex items-center justify-center">
              <Crown className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold">Premium Required</h2>
              <p className="text-sm text-muted-foreground">Unlock advanced features</p>
            </div>
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

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Feature Message */}
          <div className="p-4 bg-orange-50 dark:bg-orange-950/20 rounded-lg border border-orange-200 dark:border-orange-800">
            <p className="text-sm text-orange-700 dark:text-orange-300">
              <strong>{featureName}</strong> requires a premium subscription.
              {description && <span className="block mt-1 text-xs opacity-80">{description}</span>}
            </p>
          </div>

          {/* Benefits */}
          <div className="space-y-3">
            <p className="text-sm font-medium text-muted-foreground">Premium benefits include:</p>
            {premiumBenefits.map((benefit, index) => (
              <div key={index} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <benefit.icon className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium">{benefit.title}</p>
                  <p className="text-xs text-muted-foreground">{benefit.description}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Button
              variant="outline"
              className="flex-1"
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              className="flex-1 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700"
              onClick={onSubscribe}
            >
              Subscribe Now
              <ExternalLink className="ml-2 h-4 w-4" />
            </Button>
          </div>

          {/* Footer Note */}
          <p className="text-xs text-center text-muted-foreground">
            Your support helps us continue developing new features
          </p>
        </div>
      </div>
    </div>,
    document.body
  )
}
