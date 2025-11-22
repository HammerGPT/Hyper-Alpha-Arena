import { BarChart3, FileText, NotebookPen, Coins } from 'lucide-react'

// AI Trader icon component (custom SVG)
const AITraderIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 1024 1024" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M946 528.156a18 18 0 0 1-18-18V102a18 18 0 0 1 36 0v408.156a18 18 0 0 1-18 18zM70 527.064a18.004 18.004 0 0 1-18-18V102a18 18 0 0 1 36 0v407.06a18.004 18.004 0 0 1-18 18.004z" fill="#6E6E96"/>
    <path d="M27.016 680.908c0 30.928 25.072 56 56 56H930c30.928 0 56-25.072 56-56v-115.844c0-30.928-25.072-56-56-56H83.016c-30.928 0-56 25.072-56 56v115.844z" fill="#54BCE8"/>
    <path d="M930 754.916H83.016c-40.804 0-74-33.196-74-74v-115.852c0-40.804 33.196-74 74-74H930c40.804 0 74 33.192 74 74v115.852c0 40.804-33.196 74-74 74zM83.016 527.064c-20.952 0-38 17.048-38 38v115.852c0 20.948 17.048 38 38 38H930c20.952 0 38-17.052 38-38v-115.852c0-20.952-17.048-38-38-38H83.016z" fill="#6E6E96"/>
    <path d="M881.236 835.864c0 68.1-55.716 123.816-123.812 123.816H258.612c-68.1 0-123.816-55.716-123.816-123.816v-425.76c0-68.1 55.716-123.816 123.816-123.816h498.804c68.1 0 123.82 55.716 123.82 123.816v425.76z" fill="#7FDDFF"/>
    <path d="M345.284 575.208m-114.972 0a114.972 114.972 0 1 0 229.944 0 114.972 114.972 0 1 0-229.944 0Z" fill="#E6E8F3"/>
    <path d="M672.08 575.208m-114.972 0a114.972 114.972 0 1 0 229.944 0 114.972 114.972 0 1 0-229.944 0Z" fill="#E6E8F3"/>
    <path d="M320 555.208h48.792V604H320zM647.688 555.208h48.792V604h-48.792zM374.76 782h274.484v36H374.76z" fill="#6E6E96"/>
  </svg>
)

// K-Lines icon component (custom SVG)
const KLinesIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 1026 1024" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M59.733333 910.222222V51.2h-56.888889v910.222222h1024V910.222222z"/>
    <path d="M258.844444 620.088889h56.888889v-85.333333h56.888889v-227.555556h-56.888889v-56.888889h-56.888889v56.888889h-56.888888v227.555556h56.888888zM514.844444 790.755556h56.888889v-256h56.888889v-341.333334h-56.888889v-113.777778h-56.888889v113.777778h-56.888888v341.333334h56.888888zM770.844444 705.422222h56.888889v-142.222222h56.888889v-199.111111h-56.888889v-142.222222h-56.888889v142.222222h-56.888888v199.111111h56.888888z"/>
  </svg>
)

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
    { label: 'AI Trader', page: 'trader-management', icon: AITraderIcon },
    { label: 'Prompts', page: 'prompt-management', icon: NotebookPen },
    { label: 'Manual Trading', page: 'hyperliquid', icon: Coins },
    { label: 'K-Lines', page: 'klines', icon: KLinesIcon },
    { label: 'Premium', page: 'premium-features', icon: PremiumIcon },
    { label: 'System Logs', page: 'system-logs', icon: FileText },
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
              currentPage === 'trader-management'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('trader-management')}
            title="AI Trader"
          >
            <AITraderIcon className="w-5 h-5" />
            <span className="text-xs mt-1">AI Trader</span>
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
              currentPage === 'klines'
                ? 'bg-secondary/80 text-secondary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            }`}
            onClick={() => onPageChange?.('klines')}
            title="K-Lines"
          >
            <KLinesIcon className="w-5 h-5" />
            <span className="text-xs mt-1">K-Lines</span>
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
