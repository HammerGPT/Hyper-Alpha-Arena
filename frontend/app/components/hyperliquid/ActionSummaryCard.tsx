import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RefreshCw } from 'lucide-react';
import { getHyperliquidActionSummary } from '@/lib/hyperliquidApi';
import type { HyperliquidActionSummary } from '@/lib/types/hyperliquid';
import { formatTime } from '@/lib/dateTime';

interface ActionSummaryCardProps {
  accountId?: number | null;
  windowMinutes?: number;
  refreshIntervalSeconds?: number;
}

export default function ActionSummaryCard({
  accountId,
  windowMinutes = 1440,
  refreshIntervalSeconds = 60,
}: ActionSummaryCardProps) {
  const [summary, setSummary] = useState<HyperliquidActionSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    if (!accountId) {
      setSummary(null);
      return;
    }
    try {
      setLoading(true);
      const data = await getHyperliquidActionSummary({ accountId, windowMinutes });
      setSummary(data);
    } catch (error) {
      console.error('Failed to load Hyperliquid action summary', error);
    } finally {
      setLoading(false);
    }
  }, [accountId, windowMinutes]);

  useEffect(() => {
    loadSummary();
    if (refreshIntervalSeconds <= 0) {
      return;
    }
    const interval = setInterval(loadSummary, refreshIntervalSeconds * 1000);
    return () => clearInterval(interval);
  }, [loadSummary, refreshIntervalSeconds]);

  if (!accountId) {
    return (
      <Card className="p-4">
        <p className="text-sm text-gray-500">
          Connect a Hyperliquid account to see API activity.
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Hyperliquid Action Summary</h3>
          <p className="text-xs text-gray-500">
            Last {windowMinutes / 60}h •{' '}
            {summary?.generatedAt
              ? formatTime(summary.generatedAt)
              : '—'}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={loadSummary}
          disabled={loading}
          className="gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">Total API calls</span>
        <span className="font-bold text-lg">{summary?.totalActions ?? 0}</span>
      </div>

      <div className="space-y-2">
        {(summary?.byAction ?? []).map((entry) => (
          <div
            key={entry.actionType}
            className="flex items-center justify-between text-sm border rounded px-3 py-2"
          >
            <div>
              <p className="font-medium">{entry.actionType}</p>
              {entry.lastOccurrence && (
                <p className="text-xs text-gray-500">
                  Last at {formatTime(entry.lastOccurrence)}
                </p>
              )}
            </div>
            <div className="text-right">
              <p className="font-semibold">{entry.count}</p>
              {entry.errors > 0 && (
                <p className="text-xs text-red-600">{entry.errors} errors</p>
              )}
            </div>
          </div>
        ))}
        {(summary?.byAction?.length ?? 0) === 0 && (
          <p className="text-sm text-gray-500">No activity recorded in this window.</p>
        )}
      </div>
    </Card>
  );
}
