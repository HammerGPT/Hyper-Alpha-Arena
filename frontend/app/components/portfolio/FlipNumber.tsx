import { useEffect, useState, useRef } from 'react'

interface FlipNumberProps {
  value: number
  prefix?: string
  suffix?: string
  decimals?: number
  className?: string
}

/**
 * FlipNumber - A flip-board style animated number display
 *
 * Features:
 * - Individual digit flipping animation
 * - 3D perspective effect
 * - Smooth transitions
 */
export default function FlipNumber({
  value,
  prefix = '',
  suffix = '',
  decimals = 2,
  className = '',
}: FlipNumberProps) {
  const [displayValue, setDisplayValue] = useState(value)
  const [flippingIndices, setFlippingIndices] = useState<Set<number>>(new Set())
  const prevValueRef = useRef(value)

  useEffect(() => {
    if (Math.abs(value - prevValueRef.current) < 0.01) {
      return
    }

    const formatted = value.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })

    const prevFormatted = prevValueRef.current.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })

    // Find which digit positions changed
    const changedIndices = new Set<number>()
    const maxLen = Math.max(formatted.length, prevFormatted.length)

    for (let i = 0; i < maxLen; i++) {
      if (formatted[i] !== prevFormatted[i]) {
        changedIndices.add(i)
      }
    }

    if (changedIndices.size > 0) {
      setFlippingIndices(changedIndices)

      // Update display value after a brief delay to trigger animation
      setTimeout(() => {
        setDisplayValue(value)
      }, 10)

      // Clear flipping state after animation completes
      setTimeout(() => {
        setFlippingIndices(new Set())
      }, 900)
    } else {
      setDisplayValue(value)
    }

    prevValueRef.current = value
  }, [value, decimals])

  const formatted = displayValue.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })

  const fullDisplay = `${prefix}${formatted}${suffix}`

  return (
    <span className={`flip-number-container ${className}`}>
      {fullDisplay.split('').map((char, index) => {
        const isFlipping = flippingIndices.has(index)

        return (
          <span
            key={`${index}-${char}`}
            className={`flip-digit ${isFlipping ? 'flipping' : ''}`}
            style={{
              display: 'inline-block',
              transformStyle: 'preserve-3d',
            }}
          >
            {char}
          </span>
        )
      })}
    </span>
  )
}
