import { useEffect, useState } from 'react'
import { User, LogOut, UserCog } from 'lucide-react'
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
import { useAuth } from '@/contexts/AuthContext'
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
  const { user, loading, authEnabled, logout } = useAuth()

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
                      <Avatar className="h-9 w-9">
                        <AvatarImage src={user.avatar} alt={user.displayName || user.name} />
                        <AvatarFallback className="text-xs">
                          {user.displayName?.[0] || user.name?.[0] || "U"}
                        </AvatarFallback>
                      </Avatar>
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
    </header>
  )
}
