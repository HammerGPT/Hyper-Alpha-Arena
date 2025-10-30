import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SettingsDialog } from '@/components/layout/SettingsDialog'
import StrategyPanel from '@/components/portfolio/StrategyPanel'
import { getAccounts, TradingAccount } from '@/lib/api'

export default function TraderManagement() {
  const [accounts, setAccounts] = useState<TradingAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const loadAccounts = async () => {
    try {
      const accountList = await getAccounts()
      setAccounts(accountList)
      if (accountList.length > 0 && !selectedAccountId) {
        setSelectedAccountId(accountList[0].id)
      }
    } catch (error) {
      console.error('Failed to load accounts:', error)
    }
  }

  useEffect(() => {
    loadAccounts()
  }, [refreshKey])

  const handleAccountUpdated = () => {
    setRefreshKey(prev => prev + 1)
  }

  const handleStrategyAccountChange = (accountId: number) => {
    setSelectedAccountId(accountId)
  }

  const selectedAccount = accounts.find(acc => acc.id === selectedAccountId)

  // Check if user only has default account
  const hasOnlyDefaultAccount = accounts.length === 1 &&
    accounts[0]?.name === "Default AI Trader" &&
    accounts[0]?.api_key === "default-key-please-update-in-settings"

  // Show welcome guide for new users
  if (hasOnlyDefaultAccount) {
    return (
      <div className="h-full w-full overflow-hidden flex flex-col gap-4 p-6">
        <div className="flex-shrink-0">
          <h1 className="text-2xl font-bold">Welcome to Hyper Alpha Arena!</h1>
          <p className="text-muted-foreground">Let's set up your first AI trader</p>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <Card className="max-w-md w-full">
            <CardHeader>
              <CardTitle>🤖 Setup Your AI Trader</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                We've created a default AI trader for you. To start trading, you need to:
              </p>
              <ol className="text-sm space-y-2 list-decimal list-inside">
                <li>Configure your AI model and API key</li>
                <li>Set up your trading strategy</li>
                <li>Start automated trading</li>
              </ol>
              <div className="pt-4">
                <SettingsDialog
                  open={false}
                  onOpenChange={() => {}}
                  onAccountUpdated={handleAccountUpdated}
                  embedded={false}
                />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full w-full overflow-hidden flex flex-col gap-4 p-6">
      <div className="flex-shrink-0">
        <h1 className="text-2xl font-bold">AI Trader Management</h1>
        <p className="text-muted-foreground">Manage your AI traders and configure trading strategies</p>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-6 overflow-hidden">
        {/* Left Side - Trader Management */}
        <Card className="flex flex-col overflow-hidden">
          <CardHeader>
            <CardTitle>AI Traders</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden">
            <SettingsDialog
              open={true}
              onOpenChange={() => {}}
              onAccountUpdated={handleAccountUpdated}
              embedded={true}
            />
          </CardContent>
        </Card>

        {/* Right Side - Strategy Settings */}
        <Card className="flex flex-col overflow-hidden">
          <CardHeader>
            <CardTitle>Strategy Configuration</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden">
            {selectedAccount ? (
              <StrategyPanel
                accountId={selectedAccount.id}
                accountName={selectedAccount.name}
                refreshKey={refreshKey}
                accounts={accounts}
                onAccountChange={handleStrategyAccountChange}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                Create an AI trader to configure strategies
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}