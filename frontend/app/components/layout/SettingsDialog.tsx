import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Trash2, Plus, Pencil, Eye, EyeOff } from 'lucide-react'
import { AlertDialog } from '@/components/ui/alert-dialog'
import { 
  getAccounts as getAccounts,
  createAccount as createAccount,
  updateAccount as updateAccount,
  deleteAccount as deleteAccount,
  testLLMConnection,
  type TradingAccount,
  type TradingAccountCreate
} from '@/lib/api'

interface SettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onAccountUpdated?: () => void  // Add callback for when account is updated
  embedded?: boolean  // Add embedded mode support
}

interface AIAccount extends TradingAccount {
  model?: string
  base_url?: string
  api_key?: string
}

interface AIAccountCreate extends TradingAccountCreate {
  model?: string
  base_url?: string
  api_key?: string
}

export default function SettingsDialog({ open, onOpenChange, onAccountUpdated, embedded = false }: SettingsDialogProps) {
  const [accounts, setAccounts] = useState<AIAccount[]>([])
  const [loading, setLoading] = useState(false)
  const [toggleLoadingId, setToggleLoadingId] = useState<number | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [accountToDelete, setAccountToDelete] = useState<AIAccount | null>(null)
  const [showNewApiKey, setShowNewApiKey] = useState(false)
  const [showEditApiKey, setShowEditApiKey] = useState(false)
  const [newAccount, setNewAccount] = useState<AIAccountCreate>({
    name: '',
    model: '',
    base_url: '',
    api_key: 'default-key-please-update-in-settings',
    auto_trading_enabled: true,
  })
  const [editAccount, setEditAccount] = useState<AIAccountCreate>({
    name: '',
    model: '',
    base_url: '',
    api_key: 'default-key-please-update-in-settings',
    auto_trading_enabled: true,
  })

  const loadAccounts = async () => {
    try {
      setLoading(true)
      const data = await getAccounts()
      setAccounts(data)
    } catch (error) {
      console.error('Failed to load accounts:', error)
      toast.error('Failed to load AI traders')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      loadAccounts()
      setError(null)
      setTestResult(null)
      setShowAddForm(false)
      setEditingId(null)
      setShowNewApiKey(false)
      setShowEditApiKey(false)
    }
  }, [open])

  const handleCreateAccount = async () => {
    try {
      setLoading(true)
      setTesting(true)
      setError(null)
      setTestResult(null)

      if (!newAccount.name || !newAccount.name.trim()) {
        setError('Trader name is required')
        setLoading(false)
        setTesting(false)
        return
      }

      // If AI fields are provided, test LLM connection first
      if (newAccount.model || newAccount.base_url || newAccount.api_key) {
        setTestResult('Testing LLM connection...')
        try {
          const testResponse = await testLLMConnection({
            model: newAccount.model,
            base_url: newAccount.base_url,
            api_key: newAccount.api_key,
          })
          if (!testResponse.success) {
            const message = testResponse.message || 'LLM connection test failed'
            setError(`LLM Test Failed: ${message}`)
            setTestResult(`❌ Test failed: ${message}`)
            setLoading(false)
            setTesting(false)
            return
          }
          setTestResult('✅ LLM connection test passed! Creating AI trader...')
        } catch (testError) {
          const message = testError instanceof Error ? testError.message : 'LLM connection test failed'
          setError(`LLM Test Failed: ${message}`)
          setTestResult(`❌ Test failed: ${message}`)
          setLoading(false)
          setTesting(false)
          return
        }
      }

      console.log('Creating account with data:', newAccount)
      await createAccount(newAccount)
      setNewAccount({ name: '', model: '', base_url: '', api_key: 'default-key-please-update-in-settings', auto_trading_enabled: true })
      setShowAddForm(false)
      setShowNewApiKey(false)
      await loadAccounts()

      toast.success('AI trader created successfully!')

      // Notify parent component that account was created
      onAccountUpdated?.()
    } catch (error) {
      console.error('Failed to create account:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to create AI trader'
      setError(errorMessage)
      toast.error(`Failed to create AI trader: ${errorMessage}`)
    } finally {
      setLoading(false)
      setTesting(false)
      setTestResult(null)
    }
  }

  const handleUpdateAccount = async () => {
    if (!editingId) return
    try {
      setLoading(true)
      setTesting(true)
      setError(null)
      setTestResult(null)
      
      if (!editAccount.name || !editAccount.name.trim()) {
        setError('Trader name is required')
        setLoading(false)
        setTesting(false)
        return
      }
      
      // Test LLM connection first if AI model data is provided
      if (editAccount.model || editAccount.base_url || editAccount.api_key) {
        setTestResult('Testing LLM connection...')
        
        try {
          const testResponse = await testLLMConnection({
            model: editAccount.model,
            base_url: editAccount.base_url,
            api_key: editAccount.api_key
          })
          
          if (!testResponse.success) {
            setError(`LLM Test Failed: ${testResponse.message}`)
            setTestResult(`❌ Test failed: ${testResponse.message}`)
            setLoading(false)
            setTesting(false)
            return
          }
          
          setTestResult('✅ LLM connection test passed!')
        } catch (testError) {
          const errorMessage = testError instanceof Error ? testError.message : 'LLM connection test failed'
          setError(`LLM Test Failed: ${errorMessage}`)
          setTestResult(`❌ Test failed: ${errorMessage}`)
          setLoading(false)
          setTesting(false)
          return
        }
      }
      
      setTesting(false)
      setTestResult('Test passed! Saving AI trader...')

      console.log('Updating account with data:', editAccount)
      await updateAccount(editingId, editAccount)
      setEditingId(null)
      setEditAccount({ name: '', model: '', base_url: '', api_key: '', auto_trading_enabled: true })
      setShowEditApiKey(false)
      setTestResult(null)
      await loadAccounts()
      
      toast.success('AI trader updated successfully!')
      
      // Notify parent component that account was updated
      onAccountUpdated?.()
    } catch (error) {
      console.error('Failed to update account:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to update AI trader'
      setError(errorMessage)
      setTestResult(null)
      toast.error(`Failed to update AI trader: ${errorMessage}`)
    } finally {
      setLoading(false)
      setTesting(false)
    }
  }

  const startEdit = (account: AIAccount) => {
    setEditingId(account.id)
    setEditAccount({
      name: account.name,
      model: account.model || '',
      base_url: account.base_url || '',
      api_key: account.api_key || '',
      auto_trading_enabled: account.auto_trading_enabled ?? true,
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditAccount({ name: '', model: '', base_url: '', api_key: 'default-key-please-update-in-settings', auto_trading_enabled: true })
    setShowEditApiKey(false)
    setTestResult(null)
    setError(null)
  }

  const handleToggleAutoTrading = async (account: AIAccount, nextValue: boolean) => {
    try {
      setToggleLoadingId(account.id)
      await updateAccount(account.id, { auto_trading_enabled: nextValue })
      setAccounts((prev) =>
        prev.map((acc) => (acc.id === account.id ? { ...acc, auto_trading_enabled: nextValue } : acc))
      )
      toast.success(nextValue ? `Auto trading enabled for ${account.name}` : `Auto trading paused for ${account.name}`)
      onAccountUpdated?.()
    } catch (error) {
      console.error('Failed to toggle auto trading:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to update trading status'
      toast.error(errorMessage)
    } finally {
      setToggleLoadingId(null)
    }
  }

  const handleDeleteClick = (account: AIAccount) => {
    setAccountToDelete(account)
    setDeleteConfirmOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!accountToDelete) return
    
    try {
      setLoading(true)
      await deleteAccount(accountToDelete.id)
      await loadAccounts()
      toast.success(`AI trader "${accountToDelete.name}" deleted successfully`)
      onAccountUpdated?.()
    } catch (error) {
      console.error('Failed to delete account:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete AI trader'
      toast.error(errorMessage)
    } finally {
      setLoading(false)
      setAccountToDelete(null)
    }
  }

  const content = (
    <>
      {!embedded && (
        <DialogHeader>
          <DialogTitle>AI Trader Management</DialogTitle>
          <DialogDescription>
            Manage your AI traders and their configurations
          </DialogDescription>
        </DialogHeader>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded">
          {error}
        </div>
      )}

        <div className="space-y-6">
          {/* Existing Accounts */}
          <div className="space-y-4 flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between">
              <Button
                onClick={() => setShowAddForm(!showAddForm)}
                size="sm"
                className="flex items-center gap-2"
              >
                <Plus className="h-4 w-4" />
                Add AI Trader
              </Button>
            </div>

            {loading && accounts.length === 0 ? (
              <div>Loading AI traders...</div>
            ) : (
              <div className="space-y-3 overflow-y-auto" style={{maxHeight: 'calc(100vh - 300px)'}}>
                {/* Add New Account Form */}
                {showAddForm && (
                  <div className="space-y-4 border rounded-lg p-4 bg-muted/50">
                    <h3 className="text-lg font-medium">Add New AI Trader</h3>
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <Input
                          placeholder="Trader name"
                          value={newAccount.name || ''}
                          onChange={(e) => setNewAccount({ ...newAccount, name: e.target.value })}
                        />
                        <Input
                          placeholder="Model (e.g., gpt-4)"
                          value={newAccount.model || ''}
                          onChange={(e) => setNewAccount({ ...newAccount, model: e.target.value })}
                        />
                      </div>
                      <Input
                        placeholder="Base URL (e.g., https://api.openai.com/v1)"
                        value={newAccount.base_url || ''}
                        onChange={(e) => setNewAccount({ ...newAccount, base_url: e.target.value })}
                      />
                      <div className="relative">
                        <Input
                          placeholder="API Key"
                          type={showNewApiKey ? "text" : "password"}
                          value={newAccount.api_key || ''}
                          onChange={(e) => setNewAccount({ ...newAccount, api_key: e.target.value })}
                          className="pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => setShowNewApiKey(!showNewApiKey)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {showNewApiKey ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                      <label className="flex items-center gap-2 text-sm text-muted-foreground">
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          checked={newAccount.auto_trading_enabled ?? true}
                          onChange={(e) => setNewAccount({ ...newAccount, auto_trading_enabled: e.target.checked })}
                        />
                        <span>Start Trading</span>
                      </label>
                      <div className="flex gap-2">
                        <Button onClick={handleCreateAccount} disabled={loading}>
                          Test and Create
                        </Button>
                        <Button variant="outline" onClick={() => setShowAddForm(false)}>
                          Cancel
                        </Button>
                      </div>
                      {testResult && (
                        <div className="text-sm text-muted-foreground">
                          {testResult}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {accounts.map((account) => (
                  <div key={account.id} className="border rounded-lg p-4">
                    {editingId === account.id ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                          <Input
                            placeholder="Trader name"
                            value={editAccount.name || ''}
                            onChange={(e) => setEditAccount({ ...editAccount, name: e.target.value })}
                          />
                          <Input
                            placeholder="Model"
                            value={editAccount.model || ''}
                            onChange={(e) => setEditAccount({ ...editAccount, model: e.target.value })}
                          />
                        </div>
                        <Input
                          placeholder="Base URL"
                          value={editAccount.base_url || ''}
                          onChange={(e) => setEditAccount({ ...editAccount, base_url: e.target.value })}
                        />
                        <div className="relative">
                          <Input
                            placeholder="API Key"
                            type={showEditApiKey ? "text" : "password"}
                            value={editAccount.api_key || ''}
                            onChange={(e) => setEditAccount({ ...editAccount, api_key: e.target.value })}
                            className="pr-10"
                          />
                          <button
                            type="button"
                            onClick={() => setShowEditApiKey(!showEditApiKey)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                          >
                            {showEditApiKey ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                        <label className="flex items-center gap-2 text-sm text-muted-foreground">
                          <input
                            type="checkbox"
                            className="h-4 w-4"
                            checked={editAccount.auto_trading_enabled ?? true}
                            onChange={(e) => setEditAccount({ ...editAccount, auto_trading_enabled: e.target.checked })}
                          />
                          <span>Start Trading</span>
                        </label>
                        {testResult && (
                          <div className={`text-xs p-2 rounded ${
                            testResult.includes('❌') 
                              ? 'bg-red-50 text-red-700 border border-red-200' 
                              : 'bg-green-50 text-green-700 border border-green-200'
                          }`}>
                            {testResult}
                          </div>
                        )}
                        <div className="flex gap-2">
                          <Button onClick={handleUpdateAccount} disabled={loading || testing} size="sm">
                            {testing ? 'Testing...' : 'Test and Save'}
                          </Button>
                          <Button onClick={cancelEdit} variant="outline" size="sm" disabled={loading || testing}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-4">
                        <div className="space-y-1 flex-1">
                          <div className="flex items-center justify-between gap-3">
                            <div className="font-medium">{account.name}</div>
                            <label className="flex items-center gap-2 text-xs text-muted-foreground whitespace-nowrap">
                              <input
                                type="checkbox"
                                className="h-4 w-4"
                                checked={account.auto_trading_enabled ?? true}
                                disabled={toggleLoadingId === account.id || loading}
                                onChange={(e) => handleToggleAutoTrading(account, e.target.checked)}
                              />
                              <span>Start Trading</span>
                            </label>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {account.model ? `Model: ${account.model}` : 'No model configured'}
                          </div>
                          {account.base_url && (
                            <div className="text-xs text-muted-foreground truncate">
                              Base URL: {account.base_url}
                            </div>
                          )}
                          {account.api_key && (
                            <div className="text-xs text-muted-foreground truncate max-w-full">
                              API Key: {'*'.repeat(Math.min(20, Math.max(0, (account.api_key?.length || 0) - 4)))}{account.api_key?.slice(-4) || '****'}
                            </div>
                          )}
                          <div className="text-xs text-muted-foreground">
                            Cash: ${account.current_cash?.toLocaleString() || '0'}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            onClick={() => startEdit(account)}
                            variant="outline"
                            size="sm"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            onClick={() => handleDeleteClick(account)}
                            variant="outline"
                            size="sm"
                            disabled={loading}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
    </>
  )

  if (embedded) {
    return (
      <>
        {content}
        <AlertDialog
          open={deleteConfirmOpen}
          onOpenChange={setDeleteConfirmOpen}
          title="Delete AI Trader"
          description={`Are you sure you want to delete "${accountToDelete?.name}"? This action cannot be undone. All trading history and positions will be preserved but the trader will be deactivated.`}
          confirmText="Delete"
          cancelText="Cancel"
          variant="destructive"
          onConfirm={handleDeleteConfirm}
        />
      </>
    )
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[600px]">
          {content}
        </DialogContent>
      </Dialog>
      <AlertDialog
        open={deleteConfirmOpen}
        onOpenChange={setDeleteConfirmOpen}
        title="Delete AI Trader"
        description={`Are you sure you want to delete "${accountToDelete?.name}"? This action cannot be undone. All trading history and positions will be preserved but the trader will be deactivated.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />
    </>
  )
}

export { SettingsDialog }
