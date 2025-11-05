import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Check, X, Loader2 } from 'lucide-react';
import {
  switchEnvironment,
  getHyperliquidPositions,
  getHyperliquidConfig,
} from '@/lib/hyperliquidApi';
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid';

interface EnvironmentSwitcherProps {
  accountId: number;
  currentEnvironment: HyperliquidEnvironment;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSwitchComplete?: () => void;
}

export default function EnvironmentSwitcher({
  accountId,
  currentEnvironment,
  open,
  onOpenChange,
  onSwitchComplete,
}: EnvironmentSwitcherProps) {
  const [loading, setLoading] = useState(false);
  const [checks, setChecks] = useState({
    noOpenPositions: false,
    credentialsConfigured: false,
  });
  const [confirmations, setConfirmations] = useState({
    understandRealMoney: false,
    confirmSwitch: false,
  });

  const targetEnvironment: HyperliquidEnvironment =
    currentEnvironment === 'testnet' ? 'mainnet' : 'testnet';

  const isMainnetSwitch = targetEnvironment === 'mainnet';

  useEffect(() => {
    if (open) {
      performPreflightChecks();
      resetConfirmations();
    }
  }, [open]);

  const performPreflightChecks = async () => {
    try {
      // Check for open positions
      const positions = await getHyperliquidPositions(accountId);
      const noPositions = positions.length === 0;

      // Check if target environment credentials are configured
      const config = await getHyperliquidConfig(accountId);
      const hasCredentials =
        targetEnvironment === 'testnet'
          ? config.hasTestnetKey
          : config.hasMainnetKey;

      setChecks({
        noOpenPositions: noPositions,
        credentialsConfigured: hasCredentials,
      });
    } catch (error) {
      console.error('Preflight checks failed:', error);
    }
  };

  const resetConfirmations = () => {
    setConfirmations({
      understandRealMoney: false,
      confirmSwitch: false,
    });
  };

  const handleSwitch = async () => {
    if (!checks.noOpenPositions) {
      toast.error('Please close all open positions before switching environments');
      return;
    }

    if (!checks.credentialsConfigured) {
      toast.error(`${targetEnvironment} credentials not configured`);
      return;
    }

    if (isMainnetSwitch) {
      if (!confirmations.understandRealMoney || !confirmations.confirmSwitch) {
        toast.error('Please confirm all checkboxes to proceed');
        return;
      }
    }

    setLoading(true);
    try {
      const result = await switchEnvironment(accountId, {
        targetEnvironment,
        confirm: true,
      });

      if (result.success) {
        toast.success(
          `Successfully switched to ${targetEnvironment}`,
          { duration: 4000 }
        );
        onOpenChange(false);

        if (onSwitchComplete) {
          onSwitchComplete();
        }
      } else {
        toast.error(result.message || 'Failed to switch environment');
      }
    } catch (error: any) {
      console.error('Failed to switch environment:', error);
      toast.error(error.message || 'Failed to switch environment');
    } finally {
      setLoading(false);
    }
  };

  const allChecksPassed = checks.noOpenPositions && checks.credentialsConfigured;
  const canProceed = isMainnetSwitch
    ? allChecksPassed && confirmations.understandRealMoney && confirmations.confirmSwitch
    : allChecksPassed;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <AlertTriangle className="w-5 h-5 text-yellow-600" />
            <span>Switch Trading Environment</span>
          </DialogTitle>
          <DialogDescription>
            You are about to switch from{' '}
            <span className="font-semibold uppercase">{currentEnvironment}</span> to{' '}
            <span className="font-semibold uppercase">{targetEnvironment}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Warning for Mainnet */}
          {isMainnetSwitch && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <div className="flex items-start space-x-3">
                <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-red-900">
                    WARNING: Mainnet uses REAL MONEY
                  </p>
                  <p className="text-xs text-red-700">
                    All trades on mainnet will use real funds. Losses are permanent.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Pre-flight Checks */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Pre-flight Checks:</h3>

            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                {checks.noOpenPositions ? (
                  <Check className="w-5 h-5 text-green-600" />
                ) : (
                  <X className="w-5 h-5 text-red-600" />
                )}
                <span
                  className={`text-sm ${
                    checks.noOpenPositions ? 'text-green-700' : 'text-red-700'
                  }`}
                >
                  No open positions
                </span>
              </div>

              <div className="flex items-center space-x-2">
                {checks.credentialsConfigured ? (
                  <Check className="w-5 h-5 text-green-600" />
                ) : (
                  <X className="w-5 h-5 text-red-600" />
                )}
                <span
                  className={`text-sm ${
                    checks.credentialsConfigured ? 'text-green-700' : 'text-red-700'
                  }`}
                >
                  {targetEnvironment.charAt(0).toUpperCase() +
                    targetEnvironment.slice(1)}{' '}
                  credentials configured
                </span>
              </div>
            </div>
          </div>

          {/* Confirmations (only for mainnet switch) */}
          {isMainnetSwitch && (
            <div className="space-y-3">
              <div className="flex items-start space-x-2">
                <input
                  type="checkbox"
                  id="confirm-real-money"
                  checked={confirmations.understandRealMoney}
                  onChange={(e) =>
                    setConfirmations({
                      ...confirmations,
                      understandRealMoney: e.target.checked,
                    })
                  }
                  className="mt-1 w-4 h-4 text-red-600 rounded focus:ring-red-500"
                />
                <label htmlFor="confirm-real-money" className="text-sm">
                  I understand this is real money trading
                </label>
              </div>

              <div className="flex items-start space-x-2">
                <input
                  type="checkbox"
                  id="confirm-switch"
                  checked={confirmations.confirmSwitch}
                  onChange={(e) =>
                    setConfirmations({
                      ...confirmations,
                      confirmSwitch: e.target.checked,
                    })
                  }
                  className="mt-1 w-4 h-4 text-red-600 rounded focus:ring-red-500"
                />
                <label htmlFor="confirm-switch" className="text-sm">
                  I confirm this environment switch
                </label>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex space-x-3 pt-4">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button
              variant={isMainnetSwitch ? 'destructive' : 'default'}
              className="flex-1"
              onClick={handleSwitch}
              disabled={loading || !canProceed}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Switching...
                </>
              ) : (
                `Switch to ${targetEnvironment.charAt(0).toUpperCase() + targetEnvironment.slice(1)}`
              )}
            </Button>
          </div>

          {/* Help Text */}
          {!allChecksPassed && (
            <div className="text-xs text-gray-500 text-center pt-2">
              {!checks.noOpenPositions && (
                <p>Close all open positions before switching</p>
              )}
              {!checks.credentialsConfigured && (
                <p>Configure {targetEnvironment} credentials in settings</p>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
