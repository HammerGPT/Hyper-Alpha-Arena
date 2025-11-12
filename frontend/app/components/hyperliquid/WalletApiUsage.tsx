import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, AlertTriangle, Info } from 'lucide-react';
import toast from 'react-hot-toast';
import { getWalletRateLimit } from '@/lib/hyperliquidApi';
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid';

interface WalletApiUsageProps {
  accountId: number;
  environment: HyperliquidEnvironment;
}

interface RateLimitData {
  cumVlm: number;
  nRequestsUsed: number;
  nRequestsCap: number;
  nRequestsSurplus: number;
  remaining: number;
  usagePercent: number;
  isOverLimit: boolean;
  environment: string;
  walletAddress: string;
  timestamp?: number;
}

export default function WalletApiUsage({ accountId, environment }: WalletApiUsageProps) {
  const [rateLimit, setRateLimit] = useState<RateLimitData | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);

  // Get cache key based on account and environment
  const getCacheKey = () => `hyperliquid_rate_limit_${accountId}_${environment}`;

  // Load cached data on mount
  useEffect(() => {
    const cached = localStorage.getItem(getCacheKey());
    if (cached) {
      try {
        const data = JSON.parse(cached);
        setRateLimit(data);
        if (data.timestamp) {
          setLastUpdateTime(new Date(data.timestamp));
        }
      } catch (error) {
        console.error('Failed to parse cached rate limit data:', error);
      }
    }
  }, [accountId, environment]);

  const handleUpdate = async () => {
    setLoading(true);
    try {
      const response = await getWalletRateLimit(accountId, environment);

      if (response.success && response.rateLimit) {
        const dataWithTimestamp = {
          ...response.rateLimit,
          timestamp: Date.now(),
        };

        setRateLimit(dataWithTimestamp);
        setLastUpdateTime(new Date());

        // Save to localStorage
        localStorage.setItem(getCacheKey(), JSON.stringify(dataWithTimestamp));

        toast.success('Rate limit status updated');
      } else {
        toast.error('Failed to fetch rate limit data');
      }
    } catch (error: any) {
      console.error('Error fetching rate limit:', error);
      toast.error(error.message || 'Failed to query rate limit');
    } finally {
      setLoading(false);
    }
  };

  const getUsageColor = () => {
    if (!rateLimit) return 'bg-gray-200';
    if (rateLimit.isOverLimit) return 'bg-red-500';
    if (rateLimit.usagePercent >= 90) return 'bg-red-400';
    if (rateLimit.usagePercent >= 70) return 'bg-yellow-400';
    return 'bg-green-500';
  };

  const getUsageTextColor = () => {
    if (!rateLimit) return 'text-gray-600';
    if (rateLimit.isOverLimit) return 'text-red-600';
    if (rateLimit.usagePercent >= 90) return 'text-red-600';
    if (rateLimit.usagePercent >= 70) return 'text-yellow-600';
    return 'text-green-600';
  };

  return (
    <div className="bg-gradient-to-r from-green-50 to-emerald-50 p-6 rounded-lg border border-green-100">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Wallet API Usage</h3>
        <Button
          variant="outline"
          size="sm"
          onClick={handleUpdate}
          disabled={loading}
          className="flex items-center space-x-2"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          <span>Update</span>
        </Button>
      </div>

      {rateLimit ? (
        <div className="space-y-4">
          {/* Usage Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-500 mb-1">Cumulative Volume</p>
              <p className="text-lg font-bold">${rateLimit.cumVlm.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">Requests Used</p>
              <p className="text-lg font-bold">{rateLimit.nRequestsUsed.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">Requests Cap</p>
              <p className="text-lg font-bold">{rateLimit.nRequestsCap.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">Remaining</p>
              <p className={`text-lg font-bold ${getUsageTextColor()}`}>
                {rateLimit.remaining.toLocaleString()}
              </p>
            </div>
          </div>

          {/* Progress Bar */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-600">Usage</span>
              <span className={`text-sm font-semibold ${getUsageTextColor()}`}>
                {rateLimit.usagePercent.toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
              <div
                className={`h-full ${getUsageColor()} transition-all duration-300`}
                style={{ width: `${Math.min(rateLimit.usagePercent, 100)}%` }}
              />
            </div>
          </div>

          {/* Over Limit Warning */}
          {rateLimit.isOverLimit && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start space-x-3">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-800 mb-1">
                  ⚠️ API Quota Exceeded
                </p>
                <p className="text-xs text-red-700">
                  You have exceeded your request limit by {(rateLimit.nRequestsUsed - rateLimit.nRequestsCap).toLocaleString()} requests.
                  All order placement operations will be rejected until you increase your quota.
                </p>
                <p className="text-xs text-red-700 mt-2 font-medium">
                  💡 Solution: Trade ${(rateLimit.nRequestsUsed - rateLimit.nRequestsCap).toLocaleString()} USDC to free up quota (1 USDC = 1 request).
                </p>
              </div>
            </div>
          )}

          {/* Information Section */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-gray-700 space-y-2">
                <p>
                  <strong>What is this?</strong> Hyperliquid uses address-based request quotas to prevent API abuse.
                </p>
                <p>
                  <strong>Cumulative Volume:</strong> Total trading volume (USDC) completed on your wallet. Higher volume = more quota.
                </p>
                <p>
                  <strong>Requests Used:</strong> All API requests from your wallet, including queries (prices, positions) and orders.
                </p>
                <p>
                  <strong>Requests Cap:</strong> Maximum allowed requests = 10,000 (base) + your cumulative volume. Each $1 USDC traded adds 1 request.
                </p>
                <p>
                  <strong>What happens if exceeded?</strong> Order placement will fail with "Too many requests" error. Query operations (balance, positions, prices) are not affected.
                </p>
                <p className="font-semibold text-blue-800">
                  To increase your quota: Complete more trades. Every $1 USDC traded releases 1 request.
                </p>
              </div>
            </div>
          </div>

          {/* Last Update Time */}
          {lastUpdateTime && (
            <p className="text-xs text-gray-500 text-center">
              Last updated: {lastUpdateTime.toLocaleString()}
            </p>
          )}
        </div>
      ) : (
        <div className="text-center py-8">
          <p className="text-gray-600 mb-4">
            Click "Update" to check your wallet's API usage status
          </p>
          <Button
            onClick={handleUpdate}
            disabled={loading}
            className="flex items-center space-x-2 mx-auto"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Loading...' : 'Check Status'}</span>
          </Button>
        </div>
      )}
    </div>
  );
}
