import gptLogo from '@/components/ui/public/GPT_logo.webp'
import deepseekLogo from '@/components/ui/public/deepseek_logo.webp'
import qwenLogo from '@/components/ui/public/qwen_logo.webp'
import claudeLogo from '@/components/ui/public/Claude_logo.webp'
import geminiLogo from '@/components/ui/public/Gemini_logo.webp'
import grokLogo from '@/components/ui/public/Grok_logo.webp'

import btcIcon from '@/components/ui/public/btc.svg'
import ethIcon from '@/components/ui/public/eth.svg'
import xrpIcon from '@/components/ui/public/xrp.svg'
import dogeIcon from '@/components/ui/public/doge.svg'
import solIcon from '@/components/ui/public/sol.svg'
import bnbIcon from '@/components/ui/public/bnb.svg'

type LogoAsset = {
  src: string
  alt: string
}

const modelLogoMap: Record<string, LogoAsset> = {
  gpt: { src: gptLogo, alt: 'GPT logo' },
  deepseek: { src: deepseekLogo, alt: 'DeepSeek logo' },
  'deepseek chat': { src: deepseekLogo, alt: 'DeepSeek logo' },
  qwen: { src: qwenLogo, alt: 'Qwen logo' },
  claude: { src: claudeLogo, alt: 'Claude logo' },
  gemini: { src: geminiLogo, alt: 'Gemini logo' },
  grok: { src: grokLogo, alt: 'Grok logo' },
}

const symbolLogoMap: Record<string, LogoAsset> = {
  BTC: { src: btcIcon, alt: 'BTC icon' },
  ETH: { src: ethIcon, alt: 'ETH icon' },
  XRP: { src: xrpIcon, alt: 'XRP icon' },
  DOGE: { src: dogeIcon, alt: 'DOGE icon' },
  SOL: { src: solIcon, alt: 'SOL icon' },
  BNB: { src: bnbIcon, alt: 'BNB icon' },
}

function normalizeKey(value?: string | null) {
  if (!value) return ''
  return value.replace(/[_-]/g, ' ').trim().toLowerCase()
}

export function getModelLogo(name?: string | null) {
  if (!name) return undefined
  const normalized = normalizeKey(name)
  if (modelLogoMap[normalized]) return modelLogoMap[normalized]

  const withoutDefault = normalized.replace(/^default\s+/, '').trim()
  if (withoutDefault && modelLogoMap[withoutDefault]) {
    return modelLogoMap[withoutDefault]
  }

  // Try to match by first word (e.g., "Qwen3 Max" -> "qwen")
  const sourceForFirst = withoutDefault || normalized
  const firstWord = sourceForFirst.split(' ')[0]
  if (modelLogoMap[firstWord]) return modelLogoMap[firstWord]

  const trimmedWord = firstWord.replace(/\d+/g, '')
  return modelLogoMap[trimmedWord]
}

export function getSymbolLogo(symbol?: string | null) {
  if (!symbol) return undefined
  return symbolLogoMap[symbol.toUpperCase()]
}
