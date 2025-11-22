import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, TrendingUp, AlertTriangle } from 'lucide-react';
import { getHyperliquidBalance, calculateMarginUsageColor } from '@/lib/hyperliquidApi';
import type { HyperliquidBalance } from '@/lib/types/hyperliquid';
import { formatDateTime } from '@/lib/dateTime';

interface BalanceCardProps {
  accountId: number;
  environment: 'testnet' | 'mainnet';
  autoRefresh?: boolean;
  refreshInterval?: number; // in seconds
  refreshTrigger?: number; // external trigger for forced refresh
}

export default function BalanceCard({
  accountId,
  environment,
  autoRefresh = false,
  refreshInterval = 30,
  refreshTrigger,
}: BalanceCardProps) {
  const [balance, setBalance] = useState<HyperliquidBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);

  const getMarginStatus = (percent: number) => {
    if (percent < 50) {
      return {
        color: 'bg-green-500',
        text: 'Healthy',
        icon: TrendingUp,
        textColor: 'text-green-600',
      } as const;
    }
    if (percent < 75) {
      return {
        color: 'bg-yellow-500',
        text: 'Moderate',
        icon: AlertTriangle,
        textColor: 'text-yellow-600',
      } as const;
    }
    return {
      color: 'bg-red-500',
      text: 'High Risk',
      icon: AlertTriangle,
      textColor: 'text-red-600',
    } as const;
  };

  useEffect(() => {
    loadBalance();

    if (autoRefresh) {
      const interval = setInterval(loadBalance, refreshInterval * 1000);
      return () => clearInterval(interval);
    }
  }, [accountId, environment, autoRefresh, refreshInterval, refreshTrigger]);

  const loadBalance = async () => {
    const shouldShowSpinner = !hasLoaded;
    try {
      if (shouldShowSpinner) {
        setIsInitialLoading(true);
      }
      setError(null);
      const data = await getHyperliquidBalance(accountId, environment);
      setBalance(data);
      setHasLoaded(true);
    } catch (error: any) {
      console.error('Failed to load balance:', error);
      setError(error.message || 'Failed to load balance');
      toast.error('Failed to refresh balance');
    } finally {
      if (shouldShowSpinner) {
        setIsInitialLoading(false);
      }
    }
  };

  if (error && !hasLoaded) {
    return (
      <Card className="p-6">
        <div className="text-center space-y-4">
          <p className="text-red-600">{error}</p>
        </div>
      </Card>
    );
  }

  if (isInitialLoading) {
    return (
      <Card className="p-6">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 mx-auto animate-spin text-gray-400" />
          <p className="text-sm text-gray-500 mt-2">Loading balance...</p>
        </div>
      </Card>
    );
  }

  if (!hasLoaded || !balance) {
    return (
      <Card className="p-6">
        <div className="text-center">
          <p className="text-gray-500">No balance data available</p>
        </div>
      </Card>
    );
  }

  const marginStatus = getMarginStatus(balance.marginUsagePercent);
  const StatusIcon = marginStatus.icon;
  const lastUpdatedLabel = balance.lastUpdated
    ? formatDateTime(balance.lastUpdated)
    : null;

  return (
    <Card className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Hyperliquid Account Status</h2>
        <Badge
          variant={environment === 'testnet' ? 'default' : 'destructive'}
          className="uppercase"
        >
          {environment}
        </Badge>
      </div>
      {lastUpdatedLabel && (
        <div className="text-xs text-gray-400 -mt-4">
          Last update: {lastUpdatedLabel}
        </div>
      )}

      {/* Balance Information */}
      <div className="space-y-3">
        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600">Total Equity</span>
          <span className="text-xl font-bold">${balance.totalEquity.toFixed(2)} USDC</span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600">Available Balance</span>
          <span className="text-lg font-semibold text-green-600">
            ${balance.availableBalance.toFixed(2)}
          </span>
        </div>

        <div className="flex justify-between items-center">
          <span className="text-sm text-gray-600">Used Margin</span>
          <span className="text-lg font-semibold text-gray-700">
            ${balance.usedMargin.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <span className="text-sm font-medium">Margin Usage</span>
          <span className={`text-sm font-bold ${calculateMarginUsageColor(balance.marginUsagePercent)}`}>
            {balance.marginUsagePercent.toFixed(1)}%
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${marginStatus.color}`}
            style={{ width: `${Math.min(balance.marginUsagePercent, 100)}%` }}
          />
        </div>
        <div className="flex items-center space-x-2">
          <StatusIcon className={`w-4 h-4 ${marginStatus.textColor}`} />
          <span className={`text-sm font-medium ${marginStatus.textColor}`}>
            {marginStatus.text}
          </span>
        </div>
      </div>
    </Card>
  );
}
