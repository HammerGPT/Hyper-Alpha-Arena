/**
 * Date/Time formatting utilities
 * All functions convert UTC timestamps to user's browser local time
 * Uses 'en-US' locale for consistent English date formatting
 */

const LOCALE = 'en-US'

type DateInput = string | number | Date | null | undefined

/**
 * Parse various date inputs to Date object
 * Assumes timezone-less ISO strings are UTC (backend stores in UTC)
 */
function parseDate(input: DateInput): Date | null {
  if (!input) return null

  if (input instanceof Date) return input

  // Unix timestamp in seconds
  if (typeof input === 'number') {
    // If timestamp is in seconds (< year 3000 in ms), convert to ms
    const ts = input < 4102444800 ? input * 1000 : input
    return new Date(ts)
  }

  // Handle string input
  let dateStr = input

  // If ISO string without timezone (e.g., "2025-11-22T05:51:00" or "2025-11-22T05:51:00.001892")
  // Append 'Z' to treat as UTC (backend stores times in UTC)
  if (typeof dateStr === 'string' && dateStr.includes('T') && !dateStr.includes('+') && !dateStr.includes('Z')) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  return isNaN(date.getTime()) ? null : date
}

/**
 * Format date and time in user's local timezone
 * Output: "Nov 22, 2025, 1:30 PM" or "2025/11/22 13:30"
 */
export function formatDateTime(input: DateInput, options?: {
  style?: 'short' | 'medium' | 'long'
}): string {
  const date = parseDate(input)
  if (!date) return 'N/A'

  const style = options?.style ?? 'medium'

  if (style === 'short') {
    return date.toLocaleString(LOCALE, {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (style === 'long') {
    return date.toLocaleString(LOCALE, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  // medium (default)
  return date.toLocaleString(LOCALE, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Format date only in user's local timezone
 * Output: "Nov 22, 2025"
 */
export function formatDate(input: DateInput): string {
  const date = parseDate(input)
  if (!date) return 'N/A'

  return date.toLocaleDateString(LOCALE, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Format time only in user's local timezone
 * Output: "1:30:45 PM" or "13:30:45"
 */
export function formatTime(input: DateInput, options?: {
  showSeconds?: boolean
}): string {
  const date = parseDate(input)
  if (!date) return 'N/A'

  return date.toLocaleTimeString(LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
    ...(options?.showSeconds ? { second: '2-digit' } : {}),
  })
}

/**
 * Format relative time (e.g., "5 minutes ago", "2 hours ago")
 */
export function formatRelativeTime(input: DateInput): string {
  const date = parseDate(input)
  if (!date) return 'N/A'

  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin} min ago`
  if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`
  if (diffDay < 7) return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`

  return formatDate(date)
}

/**
 * Convert UTC timestamp to local timestamp (for charts)
 * Input: Unix timestamp in seconds (UTC)
 * Output: Unix timestamp in seconds (adjusted for local timezone display)
 */
export function utcToLocalTimestamp(utcTimestamp: number): number {
  // Get timezone offset in minutes, convert to seconds
  const offsetSeconds = new Date().getTimezoneOffset() * 60
  // Subtract offset because getTimezoneOffset returns minutes to ADD to get UTC
  // So for UTC+8, offset is -480, we need to add 8 hours = subtract -480*60
  return utcTimestamp - offsetSeconds
}

/**
 * Format timestamp for chart display (converts UTC to local)
 * For use with lightweight-charts
 */
export function formatChartTime(utcTimestamp: number): number {
  return utcToLocalTimestamp(utcTimestamp)
}
