import { Settings, BarChart3, FileText, NotebookPen, Coins } from 'lucide-react'

// Premium icon component (custom SVG)
const PremiumIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M270.218971 121.212343h483.474286a29.257143 29.257143 0 0 1 23.3472 11.644343l188.416 249.885257a29.257143 29.257143 0 0 1-1.8432 37.419886L533.942857 887.749486a29.257143 29.257143 0 0 1-43.037257 0.058514L60.416 421.595429a29.257143 29.257143 0 0 1-1.930971-37.390629l188.328228-251.260343a29.257143 29.257143 0 0 1 23.405714-11.702857z" fill="#FFA100"/>
    <path d="M768.292571 121.212343l197.163886 261.558857a29.257143 29.257143 0 0 1-1.8432 37.390629L532.714057 889.066057a11.702857 11.702857 0 0 1-20.304457-7.899428L512 257.024l256.292571-135.840914z" fill="#FFC663"/>
    <path d="M721.598171 386.340571a29.257143 29.257143 0 0 1 0.994743 1.024l22.7328 23.873829a29.257143 29.257143 0 0 1 0 40.3456l-189.410743 198.890057-22.7328 23.873829a29.257143 29.257143 0 0 1-1.726171 1.667657l1.755429-1.667657a29.4912 29.4912 0 0 1-19.456 9.0112 28.935314 28.935314 0 0 1-18.080915-4.9152 30.193371 30.193371 0 0 1-4.856685-4.096l1.960228 1.872457-0.965486-0.877714-0.994742-0.994743-22.7328-23.873829-189.410743-198.890057a29.257143 29.257143 0 0 1 0-40.374857l22.7328-23.844572a29.257143 29.257143 0 0 1 42.364343 0L512 563.960686l168.228571-176.596115a29.257143 29.257143 0 0 1 41.3696-1.024z" fill="currentColor"/>
  </svg>
)

const CommunityIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" fill="none">
    <path d="M512 512m-512 0a512 512 0 1 0 1024 0 512 512 0 1 0-1024 0Z" fill="#7AA5DA" />
    <path d="M1023.848 500.154 796.566 273.25l-370.216 451.26 266.568 266.568C886.394 917.976 1024 731.07 1024 512c0-3.962-.062-7.91-.152-11.846z" fill="#5786B5" />
    <path d="M767.434 267.04c20.412-7.964 41.512 9.896 37.03 31.34l-91.54 437.562c-4.276 20.514-28.376 29.754-45.27 17.342l-138.188-101.434-70.438 71.922c-12.378 12.62-33.72 7.482-39.03-9.344l-50.82-161.324-136.224-40.236c-17.894-5.276-18.928-30.168-1.586-36.96L767.434 267.04z m-67.198 97.09c5.964-5.276-.966-14.584-7.724-10.378l-294.03 182.354a13.362 13.362 0 0 0-5.724 15.342l40.098 176.08c.794 2.69 4.654 2.31 5-.482l8.964-134.188a13.268 13.268 0 0 1 4.414-8.55l249.002-220.178z" fill="#fff" />
    <path d="M692.514 353.752c6.758-4.206 13.688 5.102 7.724 10.378l-249 220.178a13.286 13.286 0 0 0-4.414 8.55l-8.964 134.188c-.344 2.792-4.206 3.172-5 .482l-40.098-176.08a13.36 13.36 0 0 1 5.724-15.342l294.028-182.354z" fill="#9EC2E5" />
    <path d="M434.308 729.356c-6.482-2.31-11.964-7.482-14.308-14.93l-50.82-161.324-136.224-40.236c-17.894-5.276-18.928-30.168-1.586-36.96L767.434 267.04c13.17-5.138 26.652.482 33.306 10.896a28.836 28.836 0 0 0-4.378-5.206L432.686 569.62v12.998l-2-1.448 2 81.852v65.646c.518.242 1.068.448 1.62.62v.068h.002z" fill="#fff" />
    <path d="M805.05 291.036a29.944 29.944 0 0 1-.586 7.344l-91.54 437.562c-4.276 20.514-28.376 29.754-45.27 17.342l-138.188-101.434-96.78-69.232v-12.998l363.676-296.892a28.754 28.754 0 0 1 4.378 5.206c.242.414.482.792.724 1.172.206.414.448.828.656 1.206.206.414.414.828.586 1.242.206.448.38.862.552 1.31.138.38.31.792.448 1.242.448 1.344.792 2.724 1.034 4.172.138.896.242 1.794.31 2.758z" fill="#D1D1D1" />
  </svg>
)

interface SidebarProps {
  currentPage?: string
  onPageChange?: (page: string) => void
  onAccountUpdated?: () => void  // Add callback to notify when accounts are updated
}

export default function Sidebar({ currentPage = 'comprehensive', onPageChange, onAccountUpdated }: SidebarProps) {
  const communityLink = 'https://t.me/+RqxjT7Gttm9hOGEx'

  const desktopNav = [
    { label: 'Dashboard', page: 'comprehensive', icon: BarChart3 },
    { label: 'System Logs', page: 'system-logs', icon: FileText },
    { label: 'Manual Trading', page: 'hyperliquid', icon: Coins },
    { label: 'Prompts', page: 'prompt-management', icon: NotebookPen },
    { label: 'Settings', page: 'trader-management', icon: Settings },
    { label: 'Premium', page: 'premium-features', icon: PremiumIcon },
  ] as const

  return (
    <>
      <aside className="w-16 md:w-52 border-r h-full p-4 flex flex-col fixed md:relative left-0 top-0 z-50 bg-background space-y-6">
        {/* Desktop Navigation */}
        <nav className="hidden md:flex md:flex-col md:space-y-2">
          {desktopNav.map((item) => {
            const Icon = item.icon
            const isActive = currentPage === item.page
            return (
              <button
                key={item.page}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? 'bg-secondary/80 text-secondary-foreground' : 'hover:bg-muted text-muted-foreground'
                }`}
                onClick={() => onPageChange?.(item.page)}
                title={item.label}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span>{item.label}</span>
              </button>
            )
          })}

          <button
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors hover:bg-muted text-muted-foreground"
            onClick={() => window.open(communityLink, '_blank', 'noopener,noreferrer')}
            title="Telegram Community"
          >
            <CommunityIcon className="w-5 h-5 flex-shrink-0" />
            <span>Community</span>
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
            title="Dashboard"
          >
            <BarChart3 className="w-5 h-5" />
            <span className="text-xs mt-1">Dashboard</span>
          </button>
          <button
            className={`flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors ${
              currentPage === 'hyperliquid'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('hyperliquid')}
            title="Manual Trading"
          >
            <Coins className="w-5 h-5" />
            <span className="text-xs mt-1">Manual</span>
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
          <button
            className="flex flex-col items-center justify-center w-12 h-12 rounded-lg transition-colors hover:bg-muted text-muted-foreground"
            onClick={() => window.open(communityLink, '_blank', 'noopener,noreferrer')}
            title="Community"
          >
            <CommunityIcon className="w-5 h-5" />
            <span className="text-xs mt-1">Community</span>
          </button>
        </nav>
      </aside>

    </>
  )
}
