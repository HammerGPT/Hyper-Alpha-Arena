import { useEffect, useState } from 'react'
import { User, LogOut, UserCog, ExternalLink, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import TradingModeSwitcher from '@/components/trading/TradingModeSwitcher'
import ExchangeModal from '@/components/exchange/ExchangeModal'
import { useAuth } from '@/contexts/AuthContext'
import { useCurrentExchangeInfo } from '@/contexts/ExchangeContext'
import { EXCHANGE_STATUS_COLORS } from '@/lib/types/exchange'
import { getSignInUrl } from '@/lib/auth'

interface Account {
  id: number
  user_id: number
  name: string
  account_type: string
  initial_capital: number
  current_cash: number
  frozen_cash: number
}

interface HeaderProps {
  title?: string
  currentAccount?: Account | null
  showAccountSelector?: boolean
}

export default function Header({ title = 'Hyper Alpha Arena', currentAccount, showAccountSelector = false }: HeaderProps) {
  const { user, loading, authEnabled, membership, logout } = useAuth()
  const currentExchangeInfo = useCurrentExchangeInfo()
  const [isExchangeModalOpen, setIsExchangeModalOpen] = useState(false)
  const isVipMember = membership?.status === 'ACTIVE'

  // Preload VIP icons so dropdown renders instantly
  useEffect(() => {
    ;['/static/vip_logo.png', '/static/vip_no.png'].forEach((src) => {
      const img = new Image()
      img.src = src
    })
  }, [])

  // Helper function to format membership expiry date
  const formatExpiryDate = (dateString?: string) => {
    if (!dateString) return ''
    try {
      return new Date(dateString).toLocaleDateString()
    } catch {
      return ''
    }
  }

  // Helper function to open pricing page
  const openPricingPage = () => {
    window.open('https://www.akooi.com/#pricing-section', '_blank')
  }

  const handleSignUp = async () => {
    const signInUrl = await getSignInUrl()
    if (signInUrl) {
      window.location.href = signInUrl
    }
  }

  return (
    <header className="w-full border-b bg-background/50 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="w-full py-2 px-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img src="/static/logo_app.png" alt="Logo" className="h-8 w-8 object-contain" />
          <h1 className="text-xl font-bold">{title}</h1>

          {/* Exchanges Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsExchangeModalOpen(true)}
            className="px-3 py-2 text-sm font-medium"
          >
            <span className="mr-2">🔥</span>
            Exchanges:
            <span className="ml-1 mr-1">{EXCHANGE_STATUS_COLORS[currentExchangeInfo.id]}</span>
            {currentExchangeInfo.displayName}
            <ChevronDown className="ml-2 h-3 w-3" />
          </Button>
          <span className="text-xs text-muted-foreground ml-2">Up to 30% fee discount</span>
        </div>

        <div className="flex items-center gap-3">

          <TradingModeSwitcher />

          {authEnabled && (
            <>
              {loading ? (
                <div className="w-20 h-9 bg-muted animate-pulse rounded-md" />
              ) : user ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="relative h-9 w-9 rounded-full p-0">
                      <div className={`relative rounded-full ${isVipMember ? 'p-[3px] bg-gradient-to-br from-yellow-200 via-amber-500 to-orange-600 shadow-[0_0_18px_rgba(202,138,4,0.85)]' : ''}`}>
                        {isVipMember && (
                          <>
                            <span className="pointer-events-none absolute inset-0 rounded-full bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.55),transparent_60%)] opacity-90 blur-[1px]" aria-hidden="true" />
                            <span className="pointer-events-none absolute -inset-1 rounded-full bg-[radial-gradient(circle,rgba(234,179,8,0.55),transparent_70%)] blur-xl opacity-80" aria-hidden="true" />
                          </>
                        )}
                        <div className={`relative rounded-full overflow-hidden ${isVipMember ? 'ring-2 ring-yellow-50 bg-black/70' : ''}`}>
                          <Avatar className="h-9 w-9">
                            <AvatarImage src={user.avatar} alt={user.displayName || user.name} />
                            <AvatarFallback className="text-xs">
                              {user.displayName?.[0] || user.name?.[0] || "U"}
                            </AvatarFallback>
                          </Avatar>
                        </div>
                      </div>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="w-56" align="end" forceMount>
                    <DropdownMenuLabel className="font-normal">
                      <div className="flex flex-col space-y-1">
                        <p className="text-sm font-medium leading-none">
                          {user.displayName || user.name}
                        </p>
                        <p className="text-xs leading-none text-muted-foreground">
                          {user.email}
                        </p>
                      </div>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />

                    {/* Membership Status */}
                    {membership && membership.status === 'ACTIVE' ? (
                      <DropdownMenuItem className="cursor-default">
                        <img src="/static/vip_logo.png" alt="VIP" className="mr-2 h-4 w-4" />
                        <div className="flex flex-col">
                          <span className="text-sm font-medium text-yellow-600">VIP Member</span>
                          <span className="text-xs text-muted-foreground">
                            {membership.planKey === 'yearly' ? 'Yearly Plan' : 'Monthly Plan'}
                            {membership.currentPeriodEnd && ` • Expires ${formatExpiryDate(membership.currentPeriodEnd)}`}
                          </span>
                        </div>
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onClick={openPricingPage}>
                        <img src="/static/vip_no.png" alt="Upgrade" className="mr-2 h-4 w-4" />
                        <span>Upgrade to VIP</span>
                        <ExternalLink className="ml-auto h-3 w-3" />
                      </DropdownMenuItem>
                    )}

                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => window.open('https://account.akooi.com/account', '_blank')}>
                      <UserCog className="mr-2 h-4 w-4" />
                      <span>My Account</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={logout}>
                      <LogOut className="mr-2 h-4 w-4" />
                      <span>Sign Out</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <Button
                  onClick={handleSignUp}
                  size="sm"
                  className="px-4 py-2 text-sm font-medium"
                >
                  Sign Up
                </Button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Exchange Modal */}
      <ExchangeModal
        isOpen={isExchangeModalOpen}
        onClose={() => setIsExchangeModalOpen(false)}
      />
    </header>
  )
}
