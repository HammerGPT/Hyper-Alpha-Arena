import { useEffect, useState } from 'react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { getAccounts } from '@/lib/api'

interface Account {
  id: number
  user_id?: number
  username?: string
  name: string
  account_type: string
  initial_capital: number
  current_cash: number
  frozen_cash: number
  model?: string
  is_active?: boolean
}

interface AccountWithAssets extends Account {
  total_assets: number
  positions_value: number
}

interface AccountSelectorProps {
  currentAccount: Account | null
  onAccountChange: (accountId: number) => void
  username?: string
  refreshTrigger?: number  // Add refresh trigger prop
  accounts?: AccountWithAssets[] | Account[]  // External accounts to use when provided
  loadingExternal?: boolean  // External loading state
}

// Use relative path to work with proxy

export default function AccountSelector({ currentAccount, onAccountChange, username = "default", refreshTrigger, accounts: externalAccounts, loadingExternal }: AccountSelectorProps) {
  const [accounts, setAccounts] = useState<AccountWithAssets[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // If external accounts are provided, use them and skip internal fetching
    if (externalAccounts && externalAccounts.length >= 0) {
      // Map external accounts to AccountWithAssets shape if needed
      const mapped = externalAccounts.map((a: any) => ({
        ...a,
        total_assets: (a as any).total_assets ?? ((a.current_cash || 0) + (a.frozen_cash || 0)),
        positions_value: (a as any).positions_value ?? 0,
      }))
      setAccounts(mapped)
      setLoading(loadingExternal ?? false)
      return
    }
    fetchAccounts()
  }, [username, refreshTrigger, externalAccounts, loadingExternal])  // Add refreshTrigger to dependency array

  const fetchAccounts = async () => {
    try {
      // Use default functions with hardcoded username for paper trading
      const accountData = await getAccounts()
      console.log('Fetched accounts:', accountData)
      
      // Get account-specific data for each account
      // Fast path: avoid per-account overview calls to minimize latency on page switches
      const accountsWithAssets: AccountWithAssets[] = accountData.map((account) => ({
        ...account,
        total_assets: account.current_cash + account.frozen_cash,
        positions_value: 0,
      }))
      
      setAccounts(accountsWithAssets)
    } catch (error) {
      console.error('Error fetching accounts:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="w-48">
        <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
      </div>
    )
  }

  if (accounts.length === 0) {
    return (
      <div className="w-64">
        <div className="text-xs text-muted-foreground p-2 border rounded">
          No AI traders found
        </div>
      </div>
    )
  }

  const displayName = (account: AccountWithAssets) => {
    const accountName = account.name || account.username || `${account.account_type} Trader`
    return accountName
  }

  // Find the current account in our loaded accounts list (which has total_assets)
  const currentAccountWithAssets = currentAccount 
    ? accounts.find(a => a.id === currentAccount.id) 
    : null

  return (
    <div className="w-full">
      <Select
        value={currentAccount?.id.toString() || ''}
        onValueChange={(value) => onAccountChange(parseInt(value))}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select AI Trader" className="truncate">
            <span className="truncate block">
              {currentAccountWithAssets
                ? displayName(currentAccountWithAssets)
                : currentAccount
                  ? `${currentAccount.name || 'Unknown Trader'}`
                  : 'Select AI Trader'
              }
            </span>
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {accounts.map((account) => (
            <SelectItem key={account.id} value={account.id.toString()}>
              {displayName(account)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}