import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { BarChart3, PlusCircle, List } from 'lucide-react';
import WalletSelector from './WalletSelector';
import BalanceCard from './BalanceCard';
import PositionsTable from './PositionsTable';
import OrderForm from './OrderForm';
import WalletApiUsage from './WalletApiUsage';
import type { HyperliquidEnvironment } from '@/lib/types/hyperliquid';

interface WalletOption {
  wallet_id: number
  account_id: number
  account_name: string
  model: string | null
  wallet_address: string
  environment: HyperliquidEnvironment
  is_active: boolean
  max_leverage: number
  default_leverage: number
}

const AVAILABLE_SYMBOLS = ['BTC', 'ETH', 'SOL', 'AVAX', 'MATIC', 'ARB', 'OP'];

export default function HyperliquidPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedWallet, setSelectedWallet] = useState<WalletOption | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isWalletSwitching, setIsWalletSwitching] = useState(false);

  const handleWalletSelect = (wallet: WalletOption) => {
    setIsWalletSwitching(true);
    setSelectedWallet(wallet);
    setRefreshTrigger((prev) => prev + 1);
    // Give components time to start loading, then clear switching flag
    setTimeout(() => setIsWalletSwitching(false), 300);
  };

  const handleOrderPlaced = () => {
    setRefreshTrigger((prev) => prev + 1);
    toast.success('Refreshing positions and balance');
  };

  const handlePositionClosed = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  return (
    <div className="container mx-auto p-6 h-full overflow-y-scroll">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Hyperliquid Trade</h1>
        <p className="text-gray-600 mt-1">
          Manual Trading Operations
        </p>
      </div>

      {/* Wallet Selector */}
      <div className="mb-6">
        <WalletSelector
          selectedWalletId={selectedWallet?.wallet_id || null}
          onSelect={handleWalletSelect}
        />
      </div>

      {/* Trading interface if wallet is selected and active */}
      {selectedWallet && selectedWallet.is_active && (
        <div className="relative">
          {isWalletSwitching && (
            <div className="absolute inset-0 bg-white/50 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-2"></div>
                <p className="text-sm text-gray-600">Loading wallet data...</p>
              </div>
            </div>
          )}

          <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-2 mb-6">
            <TabsTrigger value="overview" className="flex items-center space-x-2">
              <BarChart3 className="w-4 h-4" />
              <span>Overview</span>
            </TabsTrigger>
            <TabsTrigger value="trade" className="flex items-center space-x-2">
              <PlusCircle className="w-4 h-4" />
              <span>Trade</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <BalanceCard
                accountId={selectedWallet.account_id}
                environment={selectedWallet.environment}
                autoRefresh={true}
                refreshInterval={30}
                refreshTrigger={refreshTrigger}
              />

              <div className="space-y-6">
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg border border-blue-100">
                  <h3 className="text-lg font-semibold mb-3">Quick Stats</h3>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Max Leverage</span>
                      <span className="font-bold text-lg">{selectedWallet.max_leverage}x</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Default Leverage</span>
                      <span className="font-bold text-lg">{selectedWallet.default_leverage}x</span>
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
              accountId={selectedWallet.account_id}
              environment={selectedWallet.environment}
              autoRefresh={true}
              refreshInterval={30}
              refreshTrigger={refreshTrigger}
              onPositionClosed={handlePositionClosed}
            />

            <WalletApiUsage
              accountId={selectedWallet.account_id}
              environment={selectedWallet.environment}
            />
          </TabsContent>

          <TabsContent value="trade" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <OrderForm
                  accountId={selectedWallet.account_id}
                  environment={selectedWallet.environment}
                  availableSymbols={AVAILABLE_SYMBOLS}
                  maxLeverage={selectedWallet.max_leverage}
                  defaultLeverage={selectedWallet.default_leverage}
                  onOrderPlaced={handleOrderPlaced}
                />
              </div>

              <div className="space-y-6">
                <BalanceCard
                  accountId={selectedWallet.account_id}
                  environment={selectedWallet.environment}
                  autoRefresh={false}
                  refreshTrigger={refreshTrigger}
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
        </Tabs>
        </div>
      )}

      {/* Disabled wallet warning */}
      {selectedWallet && !selectedWallet.is_active && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <h3 className="font-semibold text-red-900 mb-2">Wallet Disabled</h3>
          <p className="text-sm text-red-800">
            Please re-enable this wallet in the AI Traders management page before trading.
          </p>
        </div>
      )}
    </div>
  );
}
