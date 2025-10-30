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