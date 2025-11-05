import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Eye, EyeOff, AlertTriangle, Check, Loader2 } from 'lucide-react';
import {
  setupHyperliquidAccount,
  getHyperliquidConfig,
  testConnection,
  validatePrivateKey,
} from '@/lib/hyperliquidApi';
import type { HyperliquidEnvironment, SetupRequest } from '@/lib/types/hyperliquid';

interface ConfigPanelProps {
  accountId: number;
  onConfigUpdated?: () => void;
}

export default function ConfigPanel({ accountId, onConfigUpdated }: ConfigPanelProps) {
  const [enabled, setEnabled] = useState(false);
  const [environment, setEnvironment] = useState<HyperliquidEnvironment>('testnet');
  const [privateKey, setPrivateKey] = useState('');
  const [showPrivateKey, setShowPrivateKey] = useState(false);
  const [maxLeverage, setMaxLeverage] = useState(5);
  const [defaultLeverage, setDefaultLeverage] = useState(2);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'connected' | 'disconnected'>('idle');

  useEffect(() => {
    loadConfig();
  }, [accountId]);

  const loadConfig = async () => {
    try {
      const config = await getHyperliquidConfig(accountId);
      setEnabled(config.hyperliquid_enabled || config.enabled);
      setEnvironment(config.environment);
      setMaxLeverage(config.max_leverage || config.maxLeverage || 5);
      setDefaultLeverage(config.default_leverage || config.defaultLeverage || 2);

      if (config.hyperliquid_enabled || config.enabled) {
        setConnectionStatus('connected');
        setLastUpdated(new Date().toISOString());
      }
    } catch (error) {
      console.error('Failed to load Hyperliquid config:', error);
    }
  };

  const handleSave = async () => {
    // If already configured and no new private key, only validate leverage
    if (!enabled && !privateKey) {
      toast.error('Please enter private key for initial setup');
      return;
    }

    if (privateKey && !validatePrivateKey(privateKey)) {
      toast.error('Invalid private key format');
      return;
    }

    if (defaultLeverage > maxLeverage) {
      toast.error('Default leverage cannot exceed max leverage');
      return;
    }

    // If no private key provided but already enabled, we need to require it for security
    if (!privateKey && enabled) {
      toast.error('Please re-enter private key to update settings');
      return;
    }

    setLoading(true);
    try {
      const request: SetupRequest = {
        environment,
        privateKey,
        maxLeverage,
        defaultLeverage,
      };

      const result = await setupHyperliquidAccount(accountId, request);

      if (result.success) {
        setEnabled(true);
        setLastUpdated(new Date().toISOString());
        setPrivateKey(''); // Clear for security

        // Show loading toast for connection test
        const loadingToast = toast.loading('Testing connection...');
        try {
          const testResult = await testConnection(accountId);
          toast.dismiss(loadingToast);

          if (testResult.success) {
            toast.success(`Connected to ${testResult.environment}! Address: ${testResult.address}`);
            setConnectionStatus('connected');
          } else {
            toast.error('Connection test failed: ' + (testResult.message || 'Unknown error'));
            setConnectionStatus('disconnected');
          }
        } catch (testError: any) {
          toast.dismiss(loadingToast);
          toast.error('Connection test failed: ' + testError.message);
          setConnectionStatus('disconnected');
        }

        if (onConfigUpdated) {
          onConfigUpdated();
        }
      } else {
        toast.error(result.message || 'Failed to save configuration');
      }
    } catch (error: any) {
      toast.error(error.message || 'Failed to save configuration');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="p-6 space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-bold">Hyperliquid Trading Configuration</h2>
        <p className="text-sm text-gray-500">
          Configure your Hyperliquid perpetual contract trading settings
        </p>
      </div>

      {/* Enable Toggle */}
      <div className="flex items-center space-x-3">
        <input
          type="checkbox"
          id="enable-hyperliquid"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
          disabled={!privateKey && !enabled}
        />
        <label htmlFor="enable-hyperliquid" className="text-sm font-medium">
          Enable Hyperliquid Trading
        </label>
      </div>

      {/* Environment Selector */}
      <div className="space-y-2">
        <label className="block text-sm font-medium">Environment</label>
        <div className="space-y-2">
          <label className="flex items-center space-x-2">
            <input
              type="radio"
              value="testnet"
              checked={environment === 'testnet'}
              onChange={(e) => setEnvironment(e.target.value as HyperliquidEnvironment)}
              className="w-4 h-4 text-blue-600"
            />
            <span className="text-sm">
              <span className="font-medium">Testnet</span>
              <span className="text-gray-500 ml-2">(Recommended for testing)</span>
            </span>
          </label>

          <label className="flex items-center space-x-2">
            <input
              type="radio"
              value="mainnet"
              checked={environment === 'mainnet'}
              onChange={(e) => setEnvironment(e.target.value as HyperliquidEnvironment)}
              className="w-4 h-4 text-red-600"
            />
            <span className="text-sm flex items-center">
              <span className="font-medium">Mainnet</span>
              <span className="ml-2 flex items-center text-red-600">
                <AlertTriangle className="w-4 h-4 mr-1" />
                REAL MONEY - Use with caution
              </span>
            </span>
          </label>
        </div>
      </div>

      {/* Private Key Input */}
      <div className="space-y-2">
        <label htmlFor="private-key" className="block text-sm font-medium">
          Private Key
        </label>
        <div className="relative">
          <Input
            id="private-key"
            type={showPrivateKey ? 'text' : 'password'}
            value={privateKey}
            onChange={(e) => setPrivateKey(e.target.value)}
            placeholder="0x..."
            className="pr-10 font-mono text-sm"
          />
          <button
            type="button"
            onClick={() => setShowPrivateKey(!showPrivateKey)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
          >
            {showPrivateKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-xs text-gray-500">
          Keys are encrypted before storage. Must be 0x followed by 64 hex characters.
        </p>
      </div>

      {/* Leverage Settings */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Leverage Settings</h3>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <label htmlFor="max-leverage" className="text-sm">
              Max Leverage
            </label>
            <span className="text-sm font-medium">{maxLeverage}x</span>
          </div>
          <input
            id="max-leverage"
            type="range"
            min="1"
            max="50"
            value={maxLeverage}
            onChange={(e) => setMaxLeverage(parseInt(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <label htmlFor="default-leverage" className="text-sm">
              Default Leverage
            </label>
            <span className="text-sm font-medium">{defaultLeverage}x</span>
          </div>
          <input
            id="default-leverage"
            type="range"
            min="1"
            max={maxLeverage}
            value={defaultLeverage}
            onChange={(e) => setDefaultLeverage(parseInt(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
        </div>
      </div>

      {/* Action Button */}
      <div>
        <Button
          onClick={handleSave}
          disabled={loading}
          className="w-full"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Saving...
            </>
          ) : enabled ? (
            'Update Configuration'
          ) : (
            'Save Configuration'
          )}
        </Button>
        {enabled && !privateKey && (
          <p className="text-xs text-amber-600 mt-2">
            Note: You need to re-enter your private key to update settings for security reasons.
          </p>
        )}
      </div>

      {/* Status Display */}
      <div className="pt-4 border-t space-y-2">
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium">Status:</span>
          {connectionStatus === 'connected' && (
            <span className="flex items-center text-green-600 text-sm">
              <Check className="w-4 h-4 mr-1" />
              Connected to {environment.charAt(0).toUpperCase() + environment.slice(1)}
            </span>
          )}
          {connectionStatus === 'disconnected' && (
            <span className="flex items-center text-red-600 text-sm">
              <AlertTriangle className="w-4 h-4 mr-1" />
              Disconnected
            </span>
          )}
          {connectionStatus === 'idle' && (
            <span className="text-gray-500 text-sm">Not configured</span>
          )}
        </div>

        {lastUpdated && (
          <p className="text-xs text-gray-500">
            Last Updated: {new Date(lastUpdated).toLocaleString()}
          </p>
        )}
      </div>
    </Card>
  );
}
