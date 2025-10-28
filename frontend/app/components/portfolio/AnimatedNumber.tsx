import { useEffect, useRef, useState } from 'react'

interface AnimatedNumberProps {
  value: number
  duration?: number
  prefix?: string
  decimals?: number
  className?: string
}

const clampDecimals = (digits?: number) => {
  if (digits === undefined) return 2
  if (digits < 0) return 0
  if (digits > 6) return 6
  return digits
}

export default function AnimatedNumber({
  value,
  duration = 600,
  prefix = '',
  decimals = 2,
  className,
}: AnimatedNumberProps) {
  const [display, setDisplay] = useState<number>(value)
  const [direction, setDirection] = useState<'up' | 'down' | 'none'>('none')
  const rafRef = useRef<number | null>(null)
  const startRef = useRef<number>(0)
  const fromRef = useRef<number>(value)

  useEffect(() => {
    const roundedDecimals = clampDecimals(decimals)

    const startValue = fromRef.current
    const diff = value - startValue

    // Detect direction for animation
    if (diff > 0.005) {
      setDirection('up')
    } else if (diff < -0.005) {
      setDirection('down')
    }

    if (Math.abs(diff) < 0.005) {
      setDisplay(value)
      fromRef.current = value
      setDirection('none')
      return
    }

    const step = (timestamp: number) => {
      if (!startRef.current) {
        startRef.current = timestamp
      }
      const progress = Math.min((timestamp - startRef.current) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const next = startValue + diff * eased
      setDisplay(Number(next.toFixed(roundedDecimals + 1)))

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(step)
      } else {
        fromRef.current = value
        startRef.current = 0
        rafRef.current = null
        setDisplay(Number(value.toFixed(roundedDecimals)))
        // Reset direction after animation completes
        setTimeout(() => setDirection('none'), 100)
      }
    }

    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
    }

    startRef.current = 0
    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [value, duration, decimals])

  const formatted = `${prefix}${display.toLocaleString('en-US', {
    minimumFractionDigits: clampDecimals(decimals),
    maximumFractionDigits: clampDecimals(decimals),
  })}`

  // Add animation class based on direction
  const animationClass = direction === 'up' ? 'number-increasing' : direction === 'down' ? 'number-decreasing' : ''
  const combinedClassName = `animated-number ${animationClass} ${className || ''}`.trim()

  return <span className={combinedClassName}>{formatted}</span>
}

