import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { ArenaTrade, ArenaModelChatEntry, ArenaPositionsAccount, ArenaAccountMeta } from '@/lib/api'

interface ArenaDataState {
  trades: ArenaTrade[]
  modelChat: ArenaModelChatEntry[]
  positions: ArenaPositionsAccount[]
  accountsMeta: ArenaAccountMeta[]
  lastFetched: number
}

interface ArenaDataContextType {
  data: Record<string, ArenaDataState>
  updateData: (accountKey: string, newData: Partial<ArenaDataState>) => void
  getData: (accountKey: string) => ArenaDataState | null
}

const ArenaDataContext = createContext<ArenaDataContextType | undefined>(undefined)

export function ArenaDataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<Record<string, ArenaDataState>>({})

  const updateData = useCallback((accountKey: string, newData: Partial<ArenaDataState>) => {
    setData(prev => {
      const existing = prev[accountKey] || {
        trades: [],
        modelChat: [],
        positions: [],
        accountsMeta: [],
        lastFetched: 0
      }

      return {
        ...prev,
        [accountKey]: {
          ...existing,
          ...newData,
          lastFetched: newData.lastFetched ?? Date.now()
        }
      }
    })
  }, [])

  const getData = useCallback((accountKey: string) => {
    return data[accountKey] || null
  }, [data])

  return (
    <ArenaDataContext.Provider value={{ data, updateData, getData }}>
      {children}
    </ArenaDataContext.Provider>
  )
}

export function useArenaData() {
  const context = useContext(ArenaDataContext)
  if (context === undefined) {
    throw new Error('useArenaData must be used within an ArenaDataProvider')
  }
  return context
}