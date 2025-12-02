/**
 * Exchange Icon Component
 * Displays SVG icons for different exchanges
 */

import React from 'react'
import { ExchangeId } from '@/lib/types/exchange'

interface ExchangeIconProps {
  exchangeId: ExchangeId
  className?: string
  size?: number
}

export default function ExchangeIcon({ exchangeId, className = '', size = 16 }: ExchangeIconProps) {
  const icons: Record<ExchangeId, JSX.Element> = {
    hyperliquid: (
      <svg
        width={size}
        height={size}
        viewBox="0 0 144 144"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
      >
        <path
          d="M144 71.6991C144 119.306 114.866 134.582 99.5156 120.98C86.8804 109.889 83.1211 86.4521 64.116 84.0456C39.9942 81.0113 37.9057 113.133 22.0334 113.133C3.5504 113.133 0 86.2428 0 72.4315C0 58.3063 3.96809 39.0542 19.736 39.0542C38.1146 39.0542 39.1588 66.5722 62.132 65.1073C85.0007 63.5379 85.4184 34.8689 100.247 22.6271C113.195 12.0593 144 23.4641 144 71.6991Z"
          fill="#072723"
        />
      </svg>
    ),
    binance: (
      <svg
        width={size}
        height={size}
        viewBox="0 0 1024 1024"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
      >
        <path
          d="M643.541333 566.613333l77.269334 77.226667-209.152 209.152-209.109334-209.152 77.269334-77.226667 131.84 132.522667 131.84-132.565333z m131.882667-131.925333L853.333333 512l-77.226666 77.226667L698.837333 512l76.586667-77.226667z m-263.722667 0l77.226667 76.586667-77.269333 77.269333L434.432 512l77.226667-77.226667z m-263.765333 0L324.565333 512l-76.586666 76.586667L170.666667 511.957333l77.226666-77.226666z m263.765333-263.765333l209.152 208.469333-77.312 77.226667-131.84-131.84-131.84 132.522666-77.312-77.226666 209.152-209.152z"
          fill="#EBBB4E"
        />
      </svg>
    ),
    aster: (
      <svg
        width={size}
        height={size}
        viewBox="0 0 19 18"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
      >
        <path
          fill="url(#aster-gradient-a)"
          d="m6.082 17.122 .42-1.942a3.476 3.476 0 0 0-3.397-4.212H1.18a9.02 9.02 0 0 0 4.902 6.154"
        />
        <path
          fill="url(#aster-gradient-b)"
          d="M6.927 17.475c.949.34 1.971.525 3.037.525 4.294 0 7.886-3.008 8.784-7.032h-5.875a5.625 5.625 0 0 0-5.498 4.435z"
        />
        <path
          fill="url(#aster-gradient-c)"
          d="M18.9 10.068q.064-.525.064-1.069a9 9 0 0 0-8.26-8.97L9.441 5.855a3.476 3.476 0 0 0 3.398 4.212z"
        />
        <path
          fill="url(#aster-gradient-d)"
          d="M9.789 0a9 9 0 0 0-8.763 10.068h2.046a5.625 5.625 0 0 0 5.497-4.435z"
        />
        <defs>
          <linearGradient id="aster-gradient-a" x1="11.58" x2="8.024" y1="0" y2="18.024" gradientUnits="userSpaceOnUse">
            <stop stopColor="#efbe84" />
            <stop offset="1" stopColor="#eaae67" />
          </linearGradient>
          <linearGradient id="aster-gradient-b" x1="11.58" x2="8.024" y1="0" y2="18.024" gradientUnits="userSpaceOnUse">
            <stop stopColor="#efbe84" />
            <stop offset="1" stopColor="#eaae67" />
          </linearGradient>
          <linearGradient id="aster-gradient-c" x1="11.58" x2="8.024" y1="0" y2="18.024" gradientUnits="userSpaceOnUse">
            <stop stopColor="#efbe84" />
            <stop offset="1" stopColor="#eaae67" />
          </linearGradient>
          <linearGradient id="aster-gradient-d" x1="11.58" x2="8.024" y1="0" y2="18.024" gradientUnits="userSpaceOnUse">
            <stop stopColor="#efbe84" />
            <stop offset="1" stopColor="#eaae67" />
          </linearGradient>
        </defs>
      </svg>
    )
  }

  return icons[exchangeId] || null
}
