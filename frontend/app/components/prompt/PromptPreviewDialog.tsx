import { useEffect, useState } from 'react'
import { toast } from 'react-hot-toast'
import {
  previewPrompt,
  getAccounts,
  getHyperliquidWatchlist,
  TradingAccount,
  PromptPreviewItem,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
// Checkbox component replacement with native HTML
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface PromptPreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  templateKey: string
  templateName: string
}

export default function PromptPreviewDialog({
  open,
  onOpenChange,
  templateKey,
  templateName,
}: PromptPreviewDialogProps) {
  const [accounts, setAccounts] = useState<TradingAccount[]>([])
  const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([])
  const [previews, setPreviews] = useState<PromptPreviewItem[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [hyperliquidWatchlist, setHyperliquidWatchlist] = useState<string[]>([])
  const [watchlistLoading, setWatchlistLoading] = useState(false)

  useEffect(() => {
    if (open) {
      loadAccounts()
      if (templateKey === 'hyperliquid') {
        loadHyperliquidWatchlist()
      }
    }
  }, [open, templateKey])

  const loadAccounts = async () => {
    setLoading(true)
    try {
      const list = await getAccounts()
      const aiAccounts = list.filter((acc) => acc.account_type === 'AI')
      setAccounts(aiAccounts)

      // Auto-select first account if available
      if (aiAccounts.length > 0 && selectedAccountIds.length === 0) {
        setSelectedAccountIds([aiAccounts[0].id])
      }
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to load AI traders')
    } finally {
      setLoading(false)
    }
  }

  const loadHyperliquidWatchlist = async () => {
    setWatchlistLoading(true)
    try {
      const response = await getHyperliquidWatchlist()
      setHyperliquidWatchlist(response.symbols ?? [])
    } catch (err) {
      console.error(err)
      toast.error('Failed to load Hyperliquid watchlist')
    } finally {
      setWatchlistLoading(false)
    }
  }

  const handleAccountToggle = (accountId: number) => {
    setSelectedAccountIds((prev) =>
      prev.includes(accountId) ? prev.filter((id) => id !== accountId) : [...prev, accountId],
    )
  }

  const handleGeneratePreview = async () => {
    if (selectedAccountIds.length === 0) {
      toast.error('Please select at least one AI trader')
      return
    }

    setGenerating(true)
    try {
      const result = await previewPrompt({
        promptTemplateKey: templateKey,
        accountIds: selectedAccountIds,
      })
      setPreviews(result.previews)
      toast.success(`Generated ${result.previews.length} preview(s)`)
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to generate preview')
    } finally {
      setGenerating(false)
    }
  }

  const handleCopyToClipboard = (text: string) => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        toast.success('Copied to clipboard')
      })
      .catch((err) => {
        console.error(err)
        toast.error('Failed to copy to clipboard')
      })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-7xl h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Prompt Preview: {templateName}</DialogTitle>
          <DialogDescription>
            Select AI traders and symbols to preview the filled prompt with real-time data
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 grid grid-cols-[300px_1fr] gap-4 overflow-hidden">
          {/* Left Panel: Selection */}
          <div className="border rounded-lg p-4 flex flex-col gap-4 overflow-auto">
            <div>
              <h3 className="text-sm font-semibold mb-2">Select AI Traders</h3>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading...</p>
              ) : accounts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No AI traders found</p>
              ) : (
                <div className="space-y-2">
                  {accounts.map((account) => (
                    <div key={account.id} className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id={`account-${account.id}`}
                        checked={selectedAccountIds.includes(account.id)}
                        onChange={() => handleAccountToggle(account.id)}
                        className="w-4 h-4 cursor-pointer"
                      />
                      <label
                        htmlFor={`account-${account.id}`}
                        className="text-sm cursor-pointer flex-1"
                      >
                        {account.name}
                        {account.model && (
                          <span className="text-xs text-muted-foreground ml-1">
                            ({account.model})
                          </span>
                        )}
                      </label>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {templateKey === 'hyperliquid' && (
              <div className="border-t pt-4">
                <h3 className="text-sm font-semibold mb-2">Hyperliquid Watchlist</h3>
                <p className="text-xs text-muted-foreground mb-2">
                  Prompt preview always uses the configured watchlist symbols
                </p>
                {watchlistLoading ? (
                  <p className="text-xs text-muted-foreground">Loading watchlist…</p>
                ) : hyperliquidWatchlist.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No symbols configured yet. Configure them under AI Trader Management.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {hyperliquidWatchlist.map((symbol) => (
                      <span
                        key={symbol}
                        className="px-2 py-1 text-xs border rounded-md bg-muted text-muted-foreground"
                      >
                        {symbol}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <Button
              onClick={handleGeneratePreview}
              disabled={generating || selectedAccountIds.length === 0}
              className="mt-4"
            >
              {generating ? 'Generating...' : 'Generate Preview'}
            </Button>
          </div>

          {/* Right Panel: Preview Results */}
          <div className="border rounded-lg flex flex-col overflow-hidden">
            {previews.length === 0 ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <div className="text-center">
                  <p className="text-sm">No previews generated yet</p>
                  <p className="text-xs mt-1">Select traders and click Generate Preview</p>
                </div>
              </div>
            ) : (
              <Tabs defaultValue={`${previews[0].accountId}`} className="flex-1 flex flex-col">
                <TabsList className="w-full justify-start overflow-x-auto flex-shrink-0">
                  {previews.map((preview) => (
                    <TabsTrigger
                      key={preview.accountId}
                      value={`${preview.accountId}`}
                      className="text-xs"
                    >
                      {preview.accountName}
                    </TabsTrigger>
                  ))}
                </TabsList>

                {previews.map((preview) => (
                  <TabsContent
                    key={preview.accountId}
                    value={`${preview.accountId}`}
                    className="flex-1 flex flex-col overflow-hidden mt-0"
                  >
                    <div className="flex items-center justify-between p-3 border-b">
                      <div>
                        <p className="text-sm font-semibold">{preview.accountName}</p>
                        {preview.symbols && preview.symbols.length > 0 && (
                          <p className="text-xs text-muted-foreground">
                            Symbols: {preview.symbols.join(', ')}
                          </p>
                        )}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopyToClipboard(preview.filledPrompt)}
                      >
                        Copy to Clipboard
                      </Button>
                    </div>

                    <ScrollArea className="flex-1 p-4">
                      <pre className="text-xs font-mono whitespace-pre-wrap break-words">
                        {preview.filledPrompt}
                      </pre>
                    </ScrollArea>
                  </TabsContent>
                ))}
              </Tabs>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
