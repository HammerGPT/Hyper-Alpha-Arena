import { useEffect, useState } from 'react'

interface HighlightWrapperProps {
  children: React.ReactNode
  isNew?: boolean
  className?: string
}

/**
 * HighlightWrapper - Highlights new items with a flash animation
 *
 * Usage:
 * <HighlightWrapper isNew={true}>
 *   <div>Your content here</div>
 * </HighlightWrapper>
 *
 * When isNew is true, the highlight animation will play once.
 */
export default function HighlightWrapper({ children, isNew = false, className = '' }: HighlightWrapperProps) {
  const [shouldHighlight, setShouldHighlight] = useState(isNew)

  useEffect(() => {
    if (isNew) {
      setShouldHighlight(true)

      // Remove highlight after animation completes (3 seconds for 3 flashes @ 1s each)
      const timeout = setTimeout(() => {
        setShouldHighlight(false)
      }, 3000)

      return () => clearTimeout(timeout)
    }
  }, [isNew])

  const combinedClassName = `${shouldHighlight ? 'animate-highlight slide-in' : ''} ${className}`.trim()

  return <div className={combinedClassName}>{children}</div>
}
