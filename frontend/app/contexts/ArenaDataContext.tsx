import React, { createContext, useContext, useState, ReactNode } from 'react'
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

  const updateData = (accountKey: string, newData: Partial<ArenaDataState>) => {
    setData(prev => ({
      ...prev,
      [accountKey]: {
        trades: [],
        modelChat: [],
        positions: [],
        accountsMeta: [],
        ...prev[accountKey],
        ...newData,
        lastFetched: newData.lastFetched ?? Date.now()
      }
    }))
  }

  const getData = (accountKey: string) => {
    return data[accountKey] || null
  }

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