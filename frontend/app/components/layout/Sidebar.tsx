import { useState, useEffect } from 'react'
import { PieChart, Settings, TrendingUp, BarChart3, FileText, NotebookPen, Coins } from 'lucide-react'

// Premium icon component (custom SVG)
const PremiumIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M270.218971 121.212343h483.474286a29.257143 29.257143 0 0 1 23.3472 11.644343l188.416 249.885257a29.257143 29.257143 0 0 1-1.8432 37.419886L533.942857 887.749486a29.257143 29.257143 0 0 1-43.037257 0.058514L60.416 421.595429a29.257143 29.257143 0 0 1-1.930971-37.390629l188.328228-251.260343a29.257143 29.257143 0 0 1 23.405714-11.702857z" fill="#FFA100"/>
    <path d="M768.292571 121.212343l197.163886 261.558857a29.257143 29.257143 0 0 1-1.8432 37.390629L532.714057 889.066057a11.702857 11.702857 0 0 1-20.304457-7.899428L512 257.024l256.292571-135.840914z" fill="#FFC663"/>
    <path d="M721.598171 386.340571a29.257143 29.257143 0 0 1 0.994743 1.024l22.7328 23.873829a29.257143 29.257143 0 0 1 0 40.3456l-189.410743 198.890057-22.7328 23.873829a29.257143 29.257143 0 0 1-1.726171 1.667657l1.755429-1.667657a29.4912 29.4912 0 0 1-19.456 9.0112 28.935314 28.935314 0 0 1-18.080915-4.9152 30.193371 30.193371 0 0 1-4.856685-4.096l1.960228 1.872457-0.965486-0.877714-0.994742-0.994743-22.7328-23.873829-189.410743-198.890057a29.257143 29.257143 0 0 1 0-40.374857l22.7328-23.844572a29.257143 29.257143 0 0 1 42.364343 0L512 563.960686l168.228571-176.596115a29.257143 29.257143 0 0 1 41.3696-1.024z" fill="currentColor"/>
  </svg>
)

interface SidebarProps {
  currentPage?: string
  onPageChange?: (page: string) => void
  onAccountUpdated?: () => void  // Add callback to notify when accounts are updated
}

export default function Sidebar({ currentPage = 'comprehensive', onPageChange, onAccountUpdated }: SidebarProps) {

  return (
    <>
      <aside className="w-16 border-r h-full p-2 flex flex-col items-center fixed md:relative left-0 top-0 z-50 bg-background md:inset-auto md:bg-transparent md:flex md:flex-col md:space-y-4 md:items-center md:justify-start md:p-2 md:w-16 md:h-full md:border-r">
        {/* Desktop Navigation */}
        <nav className="hidden md:flex md:flex-col md:space-y-4">
          <button
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-colors ${
              currentPage === 'comprehensive'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('comprehensive')}
            title="Hyper Alpha Arena"
          >
            <BarChart3 className="w-5 h-5" />
          </button>


          <button
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-colors ${
              currentPage === 'system-logs'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('system-logs')}
            title="System Logs"
          >
            <FileText className="w-5 h-5" />
          </button>

          <button
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-colors ${
              currentPage === 'hyperliquid'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('hyperliquid')}
            title="Hyperliquid Trading"
          >
            <Coins className="w-5 h-5" />
          </button>

          <button
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-colors ${
              currentPage === 'prompt-management'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('prompt-management')}
            title="Prompt Templates"
          >
            <NotebookPen className="w-5 h-5" />
          </button>

          <button
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-colors ${
              currentPage === 'trader-management'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('trader-management')}
            title="Settings"
          >
            <Settings className="w-5 h-5" />
          </button>

          <button
            className={`flex items-center justify-center w-10 h-10 rounded-lg transition-colors ${
              currentPage === 'premium-features'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('premium-features')}
            title="Premium Features"
          >
            <PremiumIcon className="w-5 h-5" />
          </button>
        </nav>

        {/* Mobile Navigation */}
        <nav className="md:hidden flex flex-row items-center justify-around fixed bottom-0 left-0 right-0 bg-background border-t h-16 px-4 z-50">
          <button
            className={`flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors ${
              currentPage === 'comprehensive'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('comprehensive')}
            title="Hyper Alpha Arena"
          >
            <BarChart3 className="w-5 h-5" />
            <span className="text-xs mt-1">Hyper Alpha Arena</span>
          </button>
          <button
            className={`flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors ${
              currentPage === 'hyperliquid'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('hyperliquid')}
            title="Hyperliquid"
          >
            <Coins className="w-5 h-5" />
            <span className="text-xs mt-1">Hyperliquid</span>
          </button>
          <button
            className={`flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors ${
              currentPage === 'prompt-management'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('prompt-management')}
            title="Prompts"
          >
            <NotebookPen className="w-5 h-5" />
            <span className="text-xs mt-1">Prompts</span>
          </button>
          <button
            className={`flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors ${
              currentPage === 'trader-management'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('trader-management')}
            title="Settings"
          >
            <Settings className="w-5 h-5" />
            <span className="text-xs mt-1">Settings</span>
          </button>
          <button
            className={`flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors ${
              currentPage === 'premium-features'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('premium-features')}
            title="Premium"
          >
            <PremiumIcon className="w-5 h-5" />
            <span className="text-xs mt-1">Premium</span>
          </button>
        </nav>
      </aside>

    </>
  )
}
