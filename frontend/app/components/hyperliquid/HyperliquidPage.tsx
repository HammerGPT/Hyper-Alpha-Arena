import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Settings, BarChart3, PlusCircle } from 'lucide-react';
import ConfigPanel from './ConfigPanel';
import BalanceCard from './BalanceCard';
import PositionsTable from './PositionsTable';
import OrderForm from './OrderForm';
import EnvironmentSwitcher from './EnvironmentSwitcher';
import { getHyperliquidConfig } from '@/lib/hyperliquidApi';
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid';

interface HyperliquidPageProps {
  accountId: number;
}

const AVAILABLE_SYMBOLS = ['BTC', 'ETH', 'SOL', 'AVAX', 'MATIC', 'ARB', 'OP'];

export default function HyperliquidPage({ accountId }: HyperliquidPageProps) {
  const [activeTab, setActiveTab] = useState('overview');
  const [config, setConfig] = useState<{
    enabled: boolean;
    environment: HyperliquidEnvironment;
    maxLeverage: number;
    defaultLeverage: number;
  } | null>(null);
  const [showEnvironmentSwitcher, setShowEnvironmentSwitcher] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    loadConfig();
  }, [accountId, refreshTrigger]);

  const loadConfig = async () => {
    try {
      const data = await getHyperliquidConfig(accountId);
      setConfig({
        enabled: data.hyperliquid_enabled || data.enabled,
        environment: data.environment,
        maxLeverage: data.max_leverage || data.maxLeverage,
        defaultLeverage: data.default_leverage || data.defaultLeverage,
      });
    } catch (error) {
      console.error('Failed to load Hyperliquid config:', error);
    }
  };

  const handleConfigUpdated = () => {
    setRefreshTrigger((prev) => prev + 1);
    toast.success('Configuration updated');
  };

  const handleOrderPlaced = () => {
    setRefreshTrigger((prev) => prev + 1);
    toast.success('Refreshing positions and balance');
  };

  const handlePositionClosed = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleEnvironmentSwitch = () => {
    setRefreshTrigger((prev) => prev + 1);
    setShowEnvironmentSwitcher(false);
  };

  if (!config) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="text-gray-600 mt-4">Loading Hyperliquid configuration...</p>
        </div>
      </div>
    );
  }

  if (!config.enabled) {
    return (
      <div className="container mx-auto p-6 h-full overflow-y-scroll">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold mb-2">Hyperliquid Trading</h1>
            <p className="text-gray-600">
              Perpetual contract trading on Hyperliquid DEX
            </p>
          </div>

          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 mb-6">
            <div className="flex items-start space-x-3">
              <Settings className="w-6 h-6 text-yellow-600 mt-1" />
              <div>
                <h3 className="font-semibold text-yellow-900 mb-2">
                  Hyperliquid Not Configured
                </h3>
                <p className="text-sm text-yellow-800 mb-4">
                  Please configure your Hyperliquid account settings below to start trading.
                </p>
              </div>
            </div>
          </div>

          <ConfigPanel accountId={accountId} onConfigUpdated={handleConfigUpdated} />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 h-full overflow-y-scroll">
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold">Hyperliquid Trading</h1>
            <p className="text-gray-600 mt-1">
              Real perpetual contract trading on Hyperliquid DEX
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <Badge
              variant={config.environment === 'testnet' ? 'default' : 'destructive'}
              className="text-sm px-3 py-1 uppercase"
            >
              {config.environment}
            </Badge>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowEnvironmentSwitcher(true)}
            >
              Switch to {config.environment === 'testnet' ? 'Mainnet' : 'Testnet'}
            </Button>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3 mb-6">
          <TabsTrigger value="overview" className="flex items-center space-x-2">
            <BarChart3 className="w-4 h-4" />
            <span>Overview</span>
          </TabsTrigger>
          <TabsTrigger value="trade" className="flex items-center space-x-2">
            <PlusCircle className="w-4 h-4" />
            <span>Trade</span>
          </TabsTrigger>
          <TabsTrigger value="settings" className="flex items-center space-x-2">
            <Settings className="w-4 h-4" />
            <span>Settings</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <BalanceCard
              accountId={accountId}
              environment={config.environment}
              autoRefresh={true}
              refreshInterval={30}
            />

            <div className="space-y-6">
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg border border-blue-100">
                <h3 className="text-lg font-semibold mb-3">Quick Stats</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Max Leverage</span>
                    <span className="font-bold text-lg">{config.maxLeverage}x</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Default Leverage</span>
                    <span className="font-bold text-lg">{config.defaultLeverage}x</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Environment</span>
                    <Badge
                      variant={config.environment === 'testnet' ? 'default' : 'destructive'}
                      className="uppercase"
                    >
                      {config.environment}
                    </Badge>
                  </div>
                </div>
              </div>

              <div className="bg-gradient-to-r from-purple-50 to-pink-50 p-6 rounded-lg border border-purple-100">
                <h3 className="text-lg font-semibold mb-3">Risk Management</h3>
                <ul className="space-y-2 text-sm text-gray-700">
                  <li>• Start with lower leverage (2-3x)</li>
                  <li>• Monitor liquidation prices closely</li>
                  <li>• Keep margin usage below 75%</li>
                  <li>• Use stop-loss orders when available</li>
                  <li>• Never risk more than you can afford to lose</li>
                </ul>
              </div>
            </div>
          </div>

            <PositionsTable
              accountId={accountId}
              environment={config.environment}
              autoRefresh={true}
              refreshInterval={30}
              onPositionClosed={handlePositionClosed}
            />
        </TabsContent>

        <TabsContent value="trade" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <OrderForm
                accountId={accountId}
                availableSymbols={AVAILABLE_SYMBOLS}
                maxLeverage={config.maxLeverage}
                defaultLeverage={config.defaultLeverage}
                onOrderPlaced={handleOrderPlaced}
              />
            </div>

            <div className="space-y-6">
              <BalanceCard
                accountId={accountId}
                environment={config.environment}
                autoRefresh={false}
              />

              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <h4 className="font-semibold text-yellow-900 mb-2 text-sm">
                  Trading Tips
                </h4>
                <ul className="space-y-1 text-xs text-yellow-800">
                  <li>• Market orders execute immediately</li>
                  <li>• Limit orders may not fill instantly</li>
                  <li>• Higher leverage = higher risk</li>
                  <li>• Check liquidation price before trading</li>
                  <li>• Close positions to free up margin</li>
                </ul>
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="settings" className="space-y-6">
          <ConfigPanel accountId={accountId} onConfigUpdated={handleConfigUpdated} />
        </TabsContent>
      </Tabs>

      <EnvironmentSwitcher
        accountId={accountId}
        currentEnvironment={config.environment}
        open={showEnvironmentSwitcher}
        onOpenChange={setShowEnvironmentSwitcher}
        onSwitchComplete={handleEnvironmentSwitch}
      />
    </div>
  );
}
