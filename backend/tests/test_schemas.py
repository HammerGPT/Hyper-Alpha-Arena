"""
Test Pydantic schemas for Phase 2 completeness and backward compatibility.
"""
import pytest
from decimal import Decimal
from schemas.account import AccountCreate, AccountUpdate, AccountOut
from schemas.order import OrderCreate, OrderOut


class TestAccountSchemas:
    """Test account-related Pydantic schemas"""

    def test_account_out_with_phase2_fields(self):
        """Test AccountOut serializes Phase 2 fields correctly"""
        account_data = {
            "id": 1,
            "user_id": 100,
            "name": "Test Trader",
            "model": "gpt-4",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test123",
            "initial_capital": 10000.0,
            "current_cash": 9500.0,
            "frozen_cash": 500.0,
            "account_type": "AI",
            "is_active": True,
            # Phase 2 fields
            "trading_mode": "LIVE",
            "exchange": "HYPERLIQUID",
            "wallet_address": "0x1234567890abcdef",
            "testnet_enabled": "false"
        }

        account = AccountOut(**account_data)

        assert account.id == 1
        assert account.trading_mode == "LIVE"
        assert account.exchange == "HYPERLIQUID"
        assert account.wallet_address == "0x1234567890abcdef"
        assert account.testnet_enabled == "false"

    def test_account_out_defaults_to_paper(self):
        """Test AccountOut defaults to PAPER mode when not specified"""
        account_data = {
            "id": 1,
            "user_id": 100,
            "name": "Test Trader",
            "model": "gpt-4",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test123",
            "initial_capital": 10000.0,
            "current_cash": 10000.0,
            "frozen_cash": 0.0,
            "account_type": "AI",
            "is_active": True
            # No Phase 2 fields provided
        }

        account = AccountOut(**account_data)

        assert account.trading_mode == "PAPER"
        assert account.exchange is None
        assert account.wallet_address is None
        assert account.testnet_enabled == "true"

    def test_account_out_backward_compatibility(self):
        """Test AccountOut works with legacy data (no Phase 2 fields)"""
        legacy_account_data = {
            "id": 2,
            "user_id": 200,
            "name": "Legacy Trader",
            "model": "gpt-3.5-turbo",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-legacy",
            "initial_capital": 5000.0,
            "current_cash": 5000.0,
            "frozen_cash": 0.0,
            "account_type": "AI",
            "is_active": False
        }

        account = AccountOut(**legacy_account_data)

        # Should have defaults for Phase 2 fields
        assert account.trading_mode == "PAPER"
        assert account.exchange is None
        assert account.testnet_enabled == "true"

    def test_account_out_trading_mode_validation(self):
        """Test trading_mode accepts valid values"""
        valid_modes = ["PAPER", "LIVE"]

        for mode in valid_modes:
            account_data = {
                "id": 1,
                "user_id": 100,
                "name": "Test",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1",
                "api_key": "test",
                "initial_capital": 10000.0,
                "current_cash": 10000.0,
                "frozen_cash": 0.0,
                "account_type": "AI",
                "is_active": True,
                "trading_mode": mode
            }

            account = AccountOut(**account_data)
            assert account.trading_mode == mode

    def test_account_create_schema(self):
        """Test AccountCreate schema structure"""
        create_data = {
            "name": "New Trader",
            "model": "gpt-4-turbo",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-new123",
            "initial_capital": 15000.0,
            "account_type": "AI"
        }

        account_create = AccountCreate(**create_data)

        assert account_create.name == "New Trader"
        assert account_create.initial_capital == 15000.0

    def test_account_update_schema(self):
        """Test AccountUpdate schema with optional fields"""
        update_data = {
            "name": "Updated Name",
            "model": "gpt-4"
        }

        account_update = AccountUpdate(**update_data)

        assert account_update.name == "Updated Name"
        assert account_update.model == "gpt-4"
        assert account_update.api_key is None  # Not updated


class TestOrderSchemas:
    """Test order-related Pydantic schemas"""

    def test_order_out_with_phase1_fields(self):
        """Test OrderOut includes Phase 1 paper trading fields"""
        order_data = {
            "id": 1,
            "order_no": "ORD-001",
            "user_id": 100,
            "symbol": "BTC",
            "name": "Bitcoin",
            "market": "CRYPTO",
            "side": "BUY",
            "order_type": "MARKET",
            "price": 50000.0,
            "quantity": 1,
            "filled_quantity": 1,
            "status": "FILLED",
            # Phase 1 fields
            "slippage": 0.00017,
            "rejection_reason": None
        }

        order = OrderOut(**order_data)

        assert order.slippage == 0.00017
        assert order.rejection_reason is None

    def test_order_out_with_phase2_fields(self):
        """Test OrderOut includes Phase 2 live trading fields"""
        order_data = {
            "id": 2,
            "order_no": "ORD-002",
            "user_id": 100,
            "symbol": "ETH",
            "name": "Ethereum",
            "market": "CRYPTO",
            "side": "SELL",
            "order_type": "LIMIT",
            "price": 3000.0,
            "quantity": 10,
            "filled_quantity": 10,
            "status": "FILLED",
            # Phase 2 fields
            "exchange_order_id": "HYPER-12345",
            "exchange": "HYPERLIQUID",
            "actual_fill_price": 3001.5
        }

        order = OrderOut(**order_data)

        assert order.exchange_order_id == "HYPER-12345"
        assert order.exchange == "HYPERLIQUID"
        assert order.actual_fill_price == 3001.5

    def test_order_out_with_rejection(self):
        """Test OrderOut with rejection_reason"""
        order_data = {
            "id": 3,
            "order_no": "ORD-003",
            "user_id": 100,
            "symbol": "BTC",
            "name": "Bitcoin",
            "market": "CRYPTO",
            "side": "BUY",
            "order_type": "MARKET",
            "price": 50000.0,
            "quantity": 1000,
            "filled_quantity": 0,
            "status": "REJECTED",
            "rejection_reason": "Insufficient liquidity for large order"
        }

        order = OrderOut(**order_data)

        assert order.status == "REJECTED"
        assert order.rejection_reason == "Insufficient liquidity for large order"
        assert order.filled_quantity == 0

    def test_order_out_backward_compatibility(self):
        """Test OrderOut works without Phase 1/2 fields"""
        legacy_order_data = {
            "id": 4,
            "order_no": "ORD-LEGACY",
            "user_id": 200,
            "symbol": "SOL",
            "name": "Solana",
            "market": "CRYPTO",
            "side": "BUY",
            "order_type": "MARKET",
            "price": 100.0,
            "quantity": 50,
            "filled_quantity": 50,
            "status": "FILLED"
            # No Phase 1/2 fields
        }

        order = OrderOut(**legacy_order_data)

        # Should have None for optional Phase 1/2 fields
        assert order.slippage is None
        assert order.rejection_reason is None
        assert order.exchange_order_id is None
        assert order.exchange is None
        assert order.actual_fill_price is None

    def test_order_out_all_fields_together(self):
        """Test OrderOut with both Phase 1 and Phase 2 fields"""
        comprehensive_order_data = {
            "id": 5,
            "order_no": "ORD-COMPREHENSIVE",
            "user_id": 100,
            "symbol": "BTC",
            "name": "Bitcoin",
            "market": "CRYPTO",
            "side": "BUY",
            "order_type": "MARKET",
            "price": 50000.0,
            "quantity": 1,
            "filled_quantity": 1,
            "status": "FILLED",
            # Phase 1
            "slippage": 0.0005,
            "rejection_reason": None,
            # Phase 2
            "exchange_order_id": "HYPER-99999",
            "exchange": "HYPERLIQUID",
            "actual_fill_price": 50025.0
        }

        order = OrderOut(**comprehensive_order_data)

        # Verify all fields present
        assert order.id == 5
        assert order.slippage == 0.0005
        assert order.exchange_order_id == "HYPER-99999"
        assert order.exchange == "HYPERLIQUID"
        assert order.actual_fill_price == 50025.0

    def test_order_create_validation(self):
        """Test OrderCreate schema validation"""
        create_data = {
            "user_id": 100,
            "symbol": "BTC",
            "name": "Bitcoin",
            "market": "US",
            "side": "BUY",
            "order_type": "MARKET",
            "price": None,
            "quantity": 1
        }

        order_create = OrderCreate(**create_data)

        assert order_create.quantity == 1
        assert order_create.side == "BUY"

    def test_order_create_quantity_validation(self):
        """Test OrderCreate rejects invalid quantity"""
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderCreate(
                user_id=100,
                symbol="BTC",
                name="Bitcoin",
                market="US",
                side="BUY",
                order_type="MARKET",
                quantity=0  # Invalid: must be positive
            )

    def test_order_out_optional_price(self):
        """Test OrderOut handles optional price field"""
        order_data = {
            "id": 6,
            "order_no": "ORD-006",
            "user_id": 100,
            "symbol": "BTC",
            "name": "Bitcoin",
            "market": "CRYPTO",
            "side": "BUY",
            "order_type": "MARKET",
            "price": None,  # Market orders may not have price
            "quantity": 1,
            "filled_quantity": 1,
            "status": "FILLED"
        }

        order = OrderOut(**order_data)

        assert order.price is None
        assert order.status == "FILLED"


class TestSchemaSerialization:
    """Test schema serialization and from_attributes"""

    def test_account_out_from_attributes(self):
        """Test AccountOut can serialize from ORM model attributes"""
        # Simulate ORM object
        class MockAccount:
            id = 1
            user_id = 100
            name = "Test"
            model = "gpt-4"
            base_url = "https://api.openai.com/v1"
            api_key = "sk-test"
            initial_capital = Decimal("10000.00")
            current_cash = Decimal("9500.00")
            frozen_cash = Decimal("500.00")
            account_type = "AI"
            is_active = True
            trading_mode = "PAPER"
            exchange = None
            wallet_address = None
            testnet_enabled = "true"

        mock_account = MockAccount()

        # Pydantic should be able to serialize this
        account = AccountOut.model_validate(mock_account)

        assert account.id == 1
        assert account.trading_mode == "PAPER"
        assert float(account.initial_capital) == 10000.00

    def test_order_out_from_attributes(self):
        """Test OrderOut can serialize from ORM model attributes"""
        class MockOrder:
            id = 1
            order_no = "ORD-001"
            user_id = 100
            symbol = "BTC"
            name = "Bitcoin"
            market = "CRYPTO"
            side = "BUY"
            order_type = "MARKET"
            price = Decimal("50000.00")
            quantity = Decimal("1.0")
            filled_quantity = Decimal("1.0")
            status = "FILLED"
            slippage = Decimal("0.00017")
            rejection_reason = None
            exchange_order_id = "HYPER-123"
            exchange = "HYPERLIQUID"
            actual_fill_price = Decimal("50008.50")

        mock_order = MockOrder()

        order = OrderOut.model_validate(mock_order)

        assert order.id == 1
        # Pydantic converts Decimal to float for API responses
        assert float(order.slippage) == pytest.approx(0.00017, rel=1e-6)
        assert order.exchange == "HYPERLIQUID"
        assert order.exchange_order_id == "HYPER-123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
