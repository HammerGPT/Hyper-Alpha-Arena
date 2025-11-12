import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { RefreshCw, TrendingUp, TrendingDown, X } from 'lucide-react';
import {
  getHyperliquidPositions,
  placeManualOrder,
  getPositionSide,
  formatPnl,
  formatLeverage,
} from '@/lib/hyperliquidApi';
import type { PositionDisplay } from '@/lib/types/hyperliquid';
import { cn } from '@/lib/utils';

interface PositionsTableProps {
  accountId: number;
  environment: 'testnet' | 'mainnet';
  autoRefresh?: boolean;
  refreshInterval?: number;
  refreshTrigger?: number; // external trigger for forced refresh
  onPositionClosed?: () => void;
  className?: string;
  showRefreshButton?: boolean;
}

export default function PositionsTable({
  accountId,
  environment,
  autoRefresh = false,
  refreshInterval = 30,
  refreshTrigger,
  onPositionClosed,
  className,
  showRefreshButton = true,
}: PositionsTableProps) {
  const [positions, setPositions] = useState<PositionDisplay[]>([]);
  const [loading, setLoading] = useState(false);
  const [closingPositionId, setClosingPositionId] = useState<string | null>(null);
  const [totalPnl, setTotalPnl] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  useEffect(() => {
    loadPositions();

    if (autoRefresh) {
      const interval = setInterval(loadPositions, refreshInterval * 1000);
      return () => clearInterval(interval);
    }
  }, [accountId, environment, autoRefresh, refreshInterval, refreshTrigger]);

  const loadPositions = async () => {
    try {
      setLoading(true);
      const data = await getHyperliquidPositions(accountId, environment);
      // Transform positions to display format
      const displayPositions: PositionDisplay[] = data.positions.map((pos) => {
        const side = getPositionSide(pos.szi);
        const sizeAbs = Math.abs(pos.szi);
        const positionValue = pos.positionValue || 0;
        const unrealized = pos.unrealizedPnl || 0;
        const marginUsed = pos.marginUsed || 0;
        const pnlPercent = positionValue !== 0 ? (unrealized / positionValue) * 100 : 0;
        const marginUsagePercent = positionValue !== 0 ? (marginUsed / positionValue) * 100 : 0;

        let riskLevel: 'low' | 'medium' | 'high' = 'low';
        if (marginUsagePercent > 75) riskLevel = 'high';
        else if (marginUsagePercent > 50) riskLevel = 'medium';

        return {
          ...pos,
          side,
          sizeAbs,
          pnlPercent,
          riskLevel,
          positionValue,
          unrealizedPnl: unrealized,
          marginUsed,
          liquidationPx: pos.liquidationPx ?? 0,
          entryPx: pos.entryPx ?? 0,
        };
      });

      setPositions(displayPositions);
      setLastUpdated(data.cachedAt ?? null);

      // Calculate total PnL
      const total = displayPositions.reduce((sum, pos) => sum + pos.unrealizedPnl, 0);
      setTotalPnl(total);
    } catch (error: any) {
      console.error('Failed to load positions:', error);
      toast.error('Failed to load positions');
    } finally {
      setLoading(false);
    }
  };

  const handleClosePosition = async (position: PositionDisplay) => {
    const positionId = `${position.coin}-${position.side}`;
    setClosingPositionId(positionId);

    try {
      // Close position by placing opposite order with reduceOnly flag
      await placeManualOrder(accountId, {
        symbol: position.coin,
        is_buy: position.side === 'SHORT', // Opposite side to close
        size: position.sizeAbs,
        order_type: 'market',
        reduce_only: true,
        environment,
      });

      toast.success(`Closed ${position.side} position for ${position.coin}`);
      await loadPositions();

      if (onPositionClosed) {
        onPositionClosed();
      }
    } catch (error: any) {
      console.error('Failed to close position:', error);
      toast.error(error.message || 'Failed to close position');
    } finally {
      setClosingPositionId(null);
    }
  };

  const pnlFormatted = formatPnl(totalPnl);

  return (
    <Card className={cn('p-6 space-y-4 h-full flex flex-col', className)}>
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h2 className="text-xl font-bold">Open Positions</h2>
          <p className="text-sm text-gray-500">
            Hyperliquid {environment.charAt(0).toUpperCase() + environment.slice(1)}
          </p>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-right">
            <p className="text-sm text-gray-600">Total Unrealized P&L</p>
            <p className={`text-lg font-bold ${pnlFormatted.color}`}>
              {pnlFormatted.icon} ${pnlFormatted.value}
            </p>
          </div>
          {lastUpdated && (
            <div className="text-xs text-gray-400 text-right">
              Last update: {new Date(lastUpdated).toLocaleTimeString()}
            </div>
          )}

          {showRefreshButton && (
            <Button
              onClick={loadPositions}
              disabled={loading}
              variant="outline"
              size="sm"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          )}
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
          <p className="text-gray-500">No open positions</p>
          <p className="text-sm text-gray-400 mt-2">
            Positions will appear here after placing orders
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto overflow-y-auto flex-1 min-h-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead className="text-right">Entry</TableHead>
                <TableHead className="text-right">Current</TableHead>
                <TableHead className="text-right">Unrealized P&L</TableHead>
                <TableHead className="text-right">Liq. Price</TableHead>
                <TableHead className="text-center">Leverage</TableHead>
                <TableHead className="text-center">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((position) => {
                const positionId = `${position.coin}-${position.side}`;
                const isClosing = closingPositionId === positionId;
                const pnl = formatPnl(position.unrealizedPnl ?? 0);
                const pnlPercent = position.pnlPercent.toFixed(2);
                const entryPx = position.entryPx ?? 0;
                const positionValue = position.positionValue ?? 0;
                const liquidationPx = position.liquidationPx ?? 0;
                const sizeAbs = position.sizeAbs ?? 0;

                return (
                  <TableRow key={positionId}>
                    <TableCell className="font-medium">{position.coin}</TableCell>
                    <TableCell>
                      <Badge
                        variant={position.side === 'LONG' ? 'default' : 'destructive'}
                        className="flex items-center w-fit"
                      >
                        {position.side === 'LONG' ? (
                          <TrendingUp className="w-3 h-3 mr-1" />
                        ) : (
                          <TrendingDown className="w-3 h-3 mr-1" />
                        )}
                        {position.side}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {sizeAbs.toFixed(4)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${entryPx.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${positionValue.toFixed(2)}
                    </TableCell>
                    <TableCell className={`text-right ${pnl.color}`}>
                      <div>
                        {pnl.icon} ${Math.abs(position.unrealizedPnl ?? 0).toFixed(2)}
                      </div>
                      <div className="text-xs">
                        ({pnlPercent}%)
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      ${liquidationPx.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline">
                        {formatLeverage(position.leverage ?? 1)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-center">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleClosePosition(position)}
                        disabled={isClosing}
                      >
                        {isClosing ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <X className="w-4 h-4" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  );
}
