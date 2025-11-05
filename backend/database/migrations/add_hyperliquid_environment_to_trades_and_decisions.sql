-- Add hyperliquid_environment field to trades table
ALTER TABLE trades ADD COLUMN hyperliquid_environment VARCHAR(20) DEFAULT NULL COMMENT 'testnet | mainnet | null (paper)';

-- Add hyperliquid_environment field to ai_decision_logs table
ALTER TABLE ai_decision_logs ADD COLUMN hyperliquid_environment VARCHAR(20) DEFAULT NULL COMMENT 'testnet | mainnet | null (paper)';

-- Add index for better query performance
CREATE INDEX idx_trades_hyperliquid_environment ON trades(hyperliquid_environment);
CREATE INDEX idx_ai_decision_logs_hyperliquid_environment ON ai_decision_logs(hyperliquid_environment);
