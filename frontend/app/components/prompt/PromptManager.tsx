import { useEffect, useMemo, useState } from 'react'
import { toast } from 'react-hot-toast'
import {
  getPromptTemplates,
  updatePromptTemplate,
  restorePromptTemplate,
  upsertPromptBinding,
  deletePromptBinding,
  getAccounts,
  PromptTemplate,
  PromptBinding,
  TradingAccount,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface BindingFormState {
  id?: number
  accountId?: number
  promptTemplateId?: number
}

const DEFAULT_BINDING_FORM: BindingFormState = {
  accountId: undefined,
  promptTemplateId: undefined,
}

export default function PromptManager() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [bindings, setBindings] = useState<PromptBinding[]>([])
  const [accounts, setAccounts] = useState<TradingAccount[]>([])
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [templateDraft, setTemplateDraft] = useState<string>('')
  const [descriptionDraft, setDescriptionDraft] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [bindingSaving, setBindingSaving] = useState(false)
  const [bindingForm, setBindingForm] = useState<BindingFormState>(DEFAULT_BINDING_FORM)

  const selectedTemplate = useMemo(
    () => templates.find((tpl) => tpl.key === selectedKey) || null,
    [templates, selectedKey],
  )

  const loadTemplates = async () => {
    setLoading(true)
    try {
      const data = await getPromptTemplates()
      setTemplates(data.templates)
      setBindings(data.bindings)

      if (!selectedKey && data.templates.length > 0) {
        const first = data.templates[0]
        setSelectedKey(first.key)
        setTemplateDraft(first.templateText)
        setDescriptionDraft(first.description ?? '')
      } else if (selectedKey) {
        const tpl = data.templates.find((item) => item.key === selectedKey)
        if (tpl) {
          setTemplateDraft(tpl.templateText)
          setDescriptionDraft(tpl.description ?? '')
        }
      }
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to load prompt templates')
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    setAccountsLoading(true)
    try {
      const list = await getAccounts()
      setAccounts(list)
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to load AI traders')
    } finally {
      setAccountsLoading(false)
    }
  }

  useEffect(() => {
    loadTemplates()
    loadAccounts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSelectTemplate = (key: string) => {
    setSelectedKey(key)
    const tpl = templates.find((item) => item.key === key)
    setTemplateDraft(tpl?.templateText ?? '')
    setDescriptionDraft(tpl?.description ?? '')
  }

  const handleSaveTemplate = async () => {
    if (!selectedKey) return
    setSaving(true)
    try {
      const updated = await updatePromptTemplate(selectedKey, {
        templateText: templateDraft,
        description: descriptionDraft,
        updatedBy: 'ui',
      })
      setTemplates((prev) =>
        prev.map((tpl) => (tpl.key === selectedKey ? { ...tpl, ...updated } : tpl)),
      )
      toast.success('Prompt template saved')
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to save prompt template')
    } finally {
      setSaving(false)
    }
  }

  const handleRestoreTemplate = async () => {
    if (!selectedKey) return
    setSaving(true)
    try {
      const restored = await restorePromptTemplate(selectedKey, 'ui')
      setTemplates((prev) =>
        prev.map((tpl) => (tpl.key === selectedKey ? { ...tpl, ...restored } : tpl)),
      )
      setTemplateDraft(restored.templateText)
      setDescriptionDraft(restored.description ?? '')
      toast.success('Prompt template restored')
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to restore prompt template')
    } finally {
      setSaving(false)
    }
  }

  const handleBindingSubmit = async () => {
    if (!bindingForm.accountId) {
      toast.error('Please select an AI trader')
      return
    }
    if (!bindingForm.promptTemplateId) {
      toast.error('Please select a prompt template')
      return
    }

    setBindingSaving(true)
    try {
      const payload = await upsertPromptBinding({
        id: bindingForm.id,
        accountId: bindingForm.accountId,
        promptTemplateId: bindingForm.promptTemplateId,
        updatedBy: 'ui',
      })

      setBindings((prev) => {
        const existingIndex = prev.findIndex((item) => item.id === payload.id)
        if (existingIndex !== -1) {
          const next = [...prev]
          next[existingIndex] = payload
          return next
        }
        return [...prev, payload].sort((a, b) => a.accountName.localeCompare(b.accountName))
      })
      setBindingForm(DEFAULT_BINDING_FORM)
      toast.success('Prompt binding saved')
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to save binding')
    } finally {
      setBindingSaving(false)
    }
  }

  const handleDeleteBinding = async (bindingId: number) => {
    try {
      await deletePromptBinding(bindingId)
      setBindings((prev) => prev.filter((item) => item.id !== bindingId))
      toast.success('Binding deleted')
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : 'Failed to delete binding')
    }
  }

  const handleEditBinding = (binding: PromptBinding) => {
    setBindingForm({
      id: binding.id,
      accountId: binding.accountId,
      promptTemplateId: binding.promptTemplateId,
    })
  }

  useEffect(() => {
    if (selectedTemplate) {
      setTemplateDraft(selectedTemplate.templateText)
      setDescriptionDraft(selectedTemplate.description ?? '')
    }
  }, [selectedTemplate])

  const accountOptions = useMemo(() => {
    return accounts
      .filter((account) => account.account_type === 'AI')
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [accounts])

  return (
    <div className="h-full w-full overflow-hidden flex flex-col gap-4">
      <div className="flex flex-col lg:flex-row gap-4 h-full overflow-hidden">
        {/* LEFT COLUMN - Template Selection + Edit Area */}
        <div className="flex-1 flex flex-col gap-4 overflow-hidden">
          <Card className="flex-1 overflow-hidden">
            <CardHeader>
              <CardTitle className="text-base">Prompt Template Editor</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 h-full overflow-hidden">
              {/* Template Selection Dropdown */}
              <div>
                <label className="text-xs uppercase text-muted-foreground">Template</label>
                <Select
                  value={selectedKey || ''}
                  onValueChange={handleSelectTemplate}
                  disabled={loading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={loading ? 'Loading...' : 'Select a template'} />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((tpl) => (
                      <SelectItem key={tpl.id} value={tpl.key}>
                        <div className="flex flex-col items-start">
                          <span className="font-semibold">{tpl.name}</span>
                          <span className="text-xs text-muted-foreground">{tpl.key}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Description Input */}
              <div>
                <label className="text-xs uppercase text-muted-foreground">Description</label>
                <Input
                  value={descriptionDraft}
                  onChange={(event) => setDescriptionDraft(event.target.value)}
                  placeholder="Prompt description"
                  disabled={!selectedTemplate || saving}
                />
              </div>

              {/* Template Text Area */}
              <div className="flex-1 flex flex-col overflow-hidden">
                <label className="text-xs uppercase text-muted-foreground">Template Text</label>
                <textarea
                  className="flex-1 w-full rounded-md border bg-background p-3 font-mono text-sm leading-relaxed focus:outline-none focus:ring-1 focus:ring-ring"
                  value={templateDraft}
                  onChange={(event) => setTemplateDraft(event.target.value)}
                  disabled={!selectedTemplate || saving}
                />
              </div>

              {/* Action Buttons */}
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={handleRestoreTemplate}
                  disabled={!selectedTemplate || saving}
                >
                  Restore Default
                </Button>
                <Button onClick={handleSaveTemplate} disabled={!selectedTemplate || saving}>
                  Save Template
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT COLUMN - Binding Management */}
        <Card className="w-full lg:w-[40rem] flex-shrink-0 overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">Account Prompt Bindings</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6 h-full overflow-hidden">
            {/* Bindings Table */}
            <div className="flex-1 overflow-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">Account</th>
                    <th className="py-2 pr-4">Model</th>
                    <th className="py-2 pr-4">Template</th>
                    <th className="py-2 pr-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {bindings.map((binding) => (
                    <tr key={binding.id} className="border-t">
                      <td className="py-2 pr-4">{binding.accountName}</td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {binding.accountModel || '—'}
                      </td>
                      <td className="py-2 pr-4">{binding.promptName}</td>
                      <td className="py-2 pr-4 text-right space-x-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEditBinding(binding)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => handleDeleteBinding(binding.id)}
                        >
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {bindings.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-4 text-center text-muted-foreground">
                        No prompt bindings configured.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Binding Form */}
            <div className="space-y-4 border-t pt-4">
              <div className="grid grid-cols-1 gap-3">
                <div>
                  <label className="text-xs uppercase text-muted-foreground">
                    AI Trader
                  </label>
                  <Select
                    value={
                      bindingForm.accountId !== undefined ? String(bindingForm.accountId) : ''
                    }
                    onValueChange={(value) =>
                      setBindingForm((prev) => ({
                        ...prev,
                        accountId: Number(value),
                      }))
                    }
                    disabled={accountsLoading}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={accountsLoading ? 'Loading...' : 'Select'} />
                    </SelectTrigger>
                    <SelectContent>
                      {accountOptions.map((account) => (
                        <SelectItem key={account.id} value={String(account.id)}>
                          {account.name}
                          {account.model ? ` (${account.model})` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="text-xs uppercase text-muted-foreground">Template</label>
                  <Select
                    value={
                      bindingForm.promptTemplateId !== undefined
                        ? String(bindingForm.promptTemplateId)
                        : ''
                    }
                    onValueChange={(value) =>
                      setBindingForm((prev) => ({
                        ...prev,
                        promptTemplateId: Number(value),
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      {templates.map((tpl) => (
                        <SelectItem key={tpl.id} value={String(tpl.id)}>
                          {tpl.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => setBindingForm(DEFAULT_BINDING_FORM)}
                  disabled={bindingSaving}
                >
                  Reset
                </Button>
                <Button onClick={handleBindingSubmit} disabled={bindingSaving}>
                  Save Binding
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
