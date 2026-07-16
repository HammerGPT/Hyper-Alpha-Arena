/**
 * Exchange Wallets Panel - Multi-exchange wallet configuration
 *
 * Collapsible accordion UI for managing wallets across multiple exchanges.
 * Each exchange section shows binding status badges with connection icons.
 */

import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useTranslation } from 'react-i18next'
import HyperliquidWalletSection from './HyperliquidWalletSection'
import BinanceWalletSection from './BinanceWalletSection'
import ExchangeIcon from '@/components/exchange/ExchangeIcon'
import { getAccountWallet } from '@/lib/hyperliquidApi'
import PaperAccountSection from './PaperAccountSection'

interface ExchangeWalletsPanelProps {
  accountId: number
  accountName: string
  onWalletConfigured?: () => void
}

interface ExchangeStatus {
  hyperliquid: { testnet: boolean; mainnet: boolean }
  binance: { testnet: boolean; mainnet: boolean }
}

// Connected icon (green link)
const ConnectedIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
    <path d="M749.348571 610.011429a31.963429 31.963429 0 0 1-22.674285-54.637715l83.894857-84.406857a179.2 179.2 0 0 0 53.394286-128.658286 181.394286 181.394286 0 0 0-53.248-129.024 182.418286 182.418286 0 0 0-257.755429 0L469.065143 297.618286a32.036571 32.036571 0 0 1-45.348572-45.129143L507.611429 168.082286a246.491429 246.491429 0 0 1 348.233142 0c46.445714 46.299429 71.972571 108.251429 71.972572 174.226285 0 66.194286-25.6 128-72.045714 174.006858L772.096 600.502857a31.963429 31.963429 0 0 1-22.747429 9.508572z m-233.252571 245.979428l84.48-83.968a32.036571 32.036571 0 0 0-45.202286-45.348571l-84.406857 84.041143a182.418286 182.418286 0 0 1-257.755428 0 182.418286 182.418286 0 0 1 0-257.609143l84.406857-83.968a32.036571 32.036571 0 0 0-45.202286-45.348572L168.009143 507.684571a246.491429 246.491429 0 0 0 0 348.16 245.613714 245.613714 0 0 0 174.08 71.972572c63.049143 0 126.098286-23.917714 174.08-71.899429zM406.528 662.674286l257.097143-257.024a32.036571 32.036571 0 0 0-45.275429-45.348572L361.325714 617.325714a32.036571 32.036571 0 1 0 45.275429 45.348572z" />
  </svg>
)

// Disconnected icon (gray broken link)
const DisconnectedIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 1024 1024" className={className} fill="currentColor">
    <path d="M411.355429 380.123429a10.020571 10.020571 0 0 1 11.556571 1.901714l45.641143 45.714286 1.901714 2.633142a10.020571 10.020571 0 0 1-1.901714 11.556572L384.731429 525.677714l113.371428 113.225143 83.529143-83.529143a10.020571 10.020571 0 0 1 14.116571 0h0.073143l45.933715 45.421715a10.020571 10.020571 0 0 1 0 14.189714L558.08 698.733714l53.979429 53.833143 1.901714 2.633143a10.020571 10.020571 0 0 1-1.901714 11.629714L484.205714 894.683429a250.587429 250.587429 0 0 1-177.664 73.581714 248.978286 248.978286 0 0 1-140.507428-43.154286L70.436571 1020.708571a10.459429 10.459429 0 0 1-14.262857 0l-53.248-53.248a10.020571 10.020571 0 0 1 0-14.189714l95.524572-95.524571a251.245714 251.245714 0 0 1 30.573714-318.025143L256.658286 411.794286a10.605714 10.605714 0 0 1 7.094857-2.925715l2.633143 0.292572a9.874286 9.874286 0 0 1 4.608 2.633143l53.979428 53.979428 83.748572-83.821714z m372.297142 407.259428l31.305143 73.947429c9.435429 22.162286 4.608 38.619429-14.409143 49.298285l-6.875428 3.364572c-24.649143 10.459429-42.203429 3.364571-52.662857-21.211429l-31.378286-74.020571c-9.362286-22.162286-4.608-38.619429 14.409143-49.298286l6.875428-3.364571c24.649143-10.459429 42.203429-3.364571 52.662858 21.284571z m109.202286-156.086857l78.262857 18.066286c23.405714 5.412571 33.938286 19.017143 31.451429 40.594285l-1.389714 7.533715c-5.997714 26.112-22.089143 36.132571-48.128 30.134857L874.788571 709.485714c-23.478857-5.412571-33.938286-19.017143-31.451428-40.667428l1.316571-7.533715c6.070857-26.038857 22.089143-36.132571 48.201143-30.061714z m60.708572-628.443429a10.459429 10.459429 0 0 1 14.262857 0l53.248 53.248a10.24 10.24 0 0 1 0 14.262858L925.476571 166.034286a251.245714 251.245714 0 0 1-30.500571 318.025143l-127.853714 127.853714a10.605714 10.605714 0 0 1-7.021715 2.925714l-2.706285-0.365714a9.874286 9.874286 0 0 1-4.534857-2.56L411.940571 270.921143l-1.901714-2.633143a10.020571 10.020571 0 0 1 1.901714-11.629714L539.794286 128.804571A250.148571 250.148571 0 0 1 717.312 55.369143a250.148571 250.148571 0 0 1 140.653714 43.008zM132.973714 216.868571l71.533715 36.498286c21.504 10.971429 28.379429 26.624 20.699428 47.030857l-3.145143 6.948572c-12.141714 23.844571-30.134857 29.696-53.979428 17.554285l-71.606857-36.425142c-21.430857-10.971429-28.306286-26.624-20.626286-47.030858l3.145143-7.021714c12.141714-23.844571 30.134857-29.696 53.979428-17.554286zM341.211429 62.171429l18.066285 78.262857c5.412571 23.478857-2.194286 38.838857-22.674285 46.08l-7.387429 2.121143c-26.112 5.997714-42.130286-4.022857-48.201143-30.134858l-18.066286-78.262857c-5.412571-23.405714 2.194286-38.765714 22.747429-46.08l7.314286-2.048c26.112-5.997714 42.203429 4.022857 48.274285 30.061715z" />
  </svg>
)

export default function ExchangeWalletsPanel({
  accountId,
  accountName,
  onWalletConfigured
}: ExchangeWalletsPanelProps) {
  const { t } = useTranslation()
  const [openSections, setOpenSections] = useState<string[]>([])
  const [status, setStatus] = useState<ExchangeStatus>({
    hyperliquid: { testnet: false, mainnet: false },
    binance: { testnet: false, mainnet: false }
  })

  // Load all exchange statuses on mount
  useEffect(() => {
    loadAllStatuses()
  }, [accountId])

  const loadAllStatuses = async () => {
    // Load Hyperliquid status
    try {
      const hlInfo = await getAccountWallet(accountId)
      setStatus(prev => ({
        ...prev,
        hyperliquid: {
          testnet: !!hlInfo.testnetWallet,
          mainnet: !!hlInfo.mainnetWallet
        }
      }))
    } catch (error) {
      console.error('Failed to load Hyperliquid status:', error)
    }

    // Load Binance status
    try {
      const res = await fetch(`/api/binance/accounts/${accountId}/config`)
      if (res.ok) {
        const data = await res.json()
        setStatus(prev => ({
          ...prev,
          binance: {
            testnet: data.testnet_configured,
            mainnet: data.mainnet_configured
          }
        }))
      }
    } catch (error) {
      console.error('Failed to load Binance status:', error)
    }
  }

  const toggleSection = (section: string) => {
    setOpenSections(prev =>
      prev.includes(section)
        ? prev.filter(s => s !== section)
        : [...prev, section]
    )
  }

  const updateStatus = (exchange: keyof ExchangeStatus, env: 'testnet' | 'mainnet', configured: boolean) => {
    setStatus(prev => ({
      ...prev,
      [exchange]: { ...prev[exchange], [env]: configured }
    }))
  }

  const renderStatusBadges = (exchangeStatus: { testnet: boolean; mainnet: boolean }) => (
    <div className="flex gap-2">
      <Badge
        variant={exchangeStatus.testnet ? "default" : "outline"}
        className={`text-xs px-2 py-0.5 h-6 flex items-center gap-1 ${
          exchangeStatus.testnet
            ? "bg-green-600 hover:bg-green-600"
            : "text-muted-foreground border-muted-foreground/30"
        }`}
      >
        {exchangeStatus.testnet ? (
          <ConnectedIcon className="h-3.5 w-3.5 text-white" />
        ) : (
          <DisconnectedIcon className="h-3.5 w-3.5" />
        )}
        Testnet
      </Badge>
      <Badge
        variant={exchangeStatus.mainnet ? "destructive" : "outline"}
        className={`text-xs px-2 py-0.5 h-6 flex items-center gap-1 ${
          exchangeStatus.mainnet
            ? ""
            : "text-muted-foreground border-muted-foreground/30"
        }`}
      >
        {exchangeStatus.mainnet ? (
          <ConnectedIcon className="h-3.5 w-3.5" />
        ) : (
          <DisconnectedIcon className="h-3.5 w-3.5" />
        )}
        Mainnet
      </Badge>
    </div>
  )

  const renderExchangeSection = (
    exchangeKey: string,
    exchangeName: string,
    exchangeStatus: { testnet: boolean; mainnet: boolean },
    SectionComponent: React.ComponentType<any>
  ) => {
    const isOpen = openSections.includes(exchangeKey)

    return (
      <Collapsible
        key={exchangeKey}
        open={isOpen}
        onOpenChange={() => toggleSection(exchangeKey)}
        className="border rounded-lg"
      >
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center justify-between p-3 hover:bg-muted/50 transition-colors">
            <div className="flex items-center gap-2">
              {isOpen ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              <ExchangeIcon exchangeId={exchangeKey as 'hyperliquid' | 'binance'} size={16} />
              <span className="font-medium text-sm">{exchangeName}</span>
            </div>
            {renderStatusBadges(exchangeStatus)}
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-3 pt-1 border-t">
            <SectionComponent
              accountId={accountId}
              accountName={accountName}
              onStatusChange={(env: 'testnet' | 'mainnet', configured: boolean) =>
                updateStatus(exchangeKey as keyof ExchangeStatus, env, configured)
              }
              onWalletConfigured={onWalletConfigured}
            />
          </div>
        </CollapsibleContent>
      </Collapsible>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-3">
        <Wallet className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-medium">{t('wallet.exchangeWallets', 'Exchange Wallets')}</h4>
      </div>

      <div className="space-y-2">
        {renderExchangeSection('hyperliquid', 'Hyperliquid', status.hyperliquid, HyperliquidWalletSection)}
        {renderExchangeSection('binance', 'Binance Futures', status.binance, BinanceWalletSection)}
      </div>

      <PaperAccountSection accountId={accountId} />
    </div>
  )
}
