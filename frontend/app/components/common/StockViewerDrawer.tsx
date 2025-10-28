import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer'
import cryptoViewer from './cryptoViewer'

interface cryptoViewerDrawerProps {
  symbol: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  cryptoList?: string[]
  onNavigate?: (direction: 'prev' | 'next') => void
  title?: string
}

export default function cryptoViewerDrawer({
  symbol,
  open,
  onOpenChange,
  cryptoList = [],
  onNavigate,
  title
}: cryptoViewerDrawerProps) {
  const [currentIndex, setCurrentIndex] = useState(-1)

  useEffect(() => {
    if (symbol && cryptoList.length > 0) {
      const index = cryptoList.findIndex(s => s === symbol)
      setCurrentIndex(index)
    }
  }, [symbol, cryptoList])

  const handlePrevious = () => {
    if (onNavigate) {
      onNavigate('prev')
    }
  }

  const handleNext = () => {
    if (onNavigate) {
      onNavigate('next')
    }
  }

  const hasPrevious = currentIndex > 0
  const hasNext = currentIndex < cryptoList.length - 1

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[90vh]">
        <DrawerHeader className="flex-row items-center justify-between space-y-0 pb-4 border-b">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={handlePrevious}
              disabled={!hasPrevious}
              className="h-8 w-8"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <DrawerTitle className="text-base">
              {title || (symbol ? `${symbol}` : 'crypto Viewer')}
              {cryptoList.length > 0 && currentIndex >= 0 && (
                <span className="text-xs text-muted-foreground ml-2">
                  ({currentIndex + 1}/{cryptoList.length})
                </span>
              )}
            </DrawerTitle>
            <Button
              variant="outline"
              size="icon"
              onClick={handleNext}
              disabled={!hasNext}
              className="h-8 w-8"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
          <DrawerClose asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <X className="h-4 w-4" />
            </Button>
          </DrawerClose>
        </DrawerHeader>
        
        <div className="overflow-y-auto flex-1 px-2">
          <cryptoViewer symbol={symbol} />
        </div>
      </DrawerContent>
    </Drawer>
  )
}
