"""
Test order API endpoints for Phase 1/2 field exposure.
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base, get_db
from main import app
from database.models import User, Account, Order


# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_orders.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(scope="function")
def setup_database():
    """Create test database and tables"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_user(setup_database):
    """Create a test user"""
    db = TestingSessionLocal()
    try:
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@pytest.fixture(scope="function")
def test_account(test_user):
    """Create a test account"""
    db = TestingSessionLocal()
    try:
        account = Account(
            user_id=test_user.id,
            version="v1",
            name="Test Trader",
            model="gpt-4",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            initial_capital=10000.0,
            current_cash=10000.0,
            frozen_cash=0.0,
            account_type="AI",
            is_active="true",
            trading_mode="PAPER"
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account
    finally:
        db.close()


@pytest.fixture(scope="function")
def paper_order_with_slippage(test_account):
    """Create a PAPER order with Phase 1 slippage"""
    db = TestingSessionLocal()
    try:
        order = Order(
            version="v1",
            account_id=test_account.id,
            order_no="ORD-PAPER-001",
            symbol="BTC",
            name="Bitcoin",
            market="CRYPTO",
            side="BUY",
            order_type="MARKET",
            price=Decimal("50000.00"),
            quantity=Decimal("1.0"),
            filled_quantity=Decimal("1.0"),
            status="FILLED",
            # Phase 1 fields
            slippage=Decimal("0.00017"),
            rejection_reason=None
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order
    finally:
        db.close()


@pytest.fixture(scope="function")
def rejected_order(test_account):
    """Create a rejected order with rejection_reason"""
    db = TestingSessionLocal()
    try:
        order = Order(
            version="v1",
            account_id=test_account.id,
            order_no="ORD-REJECTED-001",
            symbol="BTC",
            name="Bitcoin",
            market="CRYPTO",
            side="BUY",
            order_type="MARKET",
            price=Decimal("50000.00"),
            quantity=Decimal("1000.0"),  # Large order
            filled_quantity=Decimal("0.0"),
            status="REJECTED",
            # Phase 1 fields
            slippage=None,
            rejection_reason="Insufficient liquidity for large order"
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order
    finally:
        db.close()


@pytest.fixture(scope="function")
def live_order_with_exchange_data(test_account):
    """Create a LIVE order with Phase 2 exchange data"""
    db = TestingSessionLocal()
    try:
        order = Order(
            version="v1",
            account_id=test_account.id,
            order_no="ORD-LIVE-001",
            symbol="ETH",
            name="Ethereum",
            market="CRYPTO",
            side="SELL",
            order_type="LIMIT",
            price=Decimal("3000.00"),
            quantity=Decimal("10.0"),
            filled_quantity=Decimal("10.0"),
            status="FILLED",
            # Phase 1 fields
            slippage=Decimal("0.0002"),
            rejection_reason=None,
            # Phase 2 fields
            exchange_order_id="HYPER-12345",
            exchange="HYPERLIQUID",
            actual_fill_price=Decimal("3001.50")
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order
    finally:
        db.close()


class TestOrderPhase1Fields:
    """Test Phase 1 paper trading fields"""

    def test_order_includes_slippage(self, test_user, paper_order_with_slippage):
        """Test API returns slippage field"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        assert len(orders) >= 1

        order = orders[0]
        assert "slippage" in order
        assert order["slippage"] is not None
        assert float(order["slippage"]) == pytest.approx(0.00017, rel=1e-6)

    def test_order_includes_rejection_reason(self, test_user, rejected_order):
        """Test API returns rejection_reason for rejected orders"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        rejected = next((o for o in orders if o["status"] == "REJECTED"), None)
        assert rejected is not None

        assert "rejection_reason" in rejected
        assert rejected["rejection_reason"] == "Insufficient liquidity for large order"

    def test_filled_order_has_no_rejection(self, test_user, paper_order_with_slippage):
        """Test filled orders have null rejection_reason"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        filled = next((o for o in orders if o["status"] == "FILLED"), None)
        assert filled is not None

        assert "rejection_reason" in filled
        assert filled["rejection_reason"] is None


class TestOrderPhase2Fields:
    """Test Phase 2 live trading fields"""

    def test_order_includes_exchange_order_id(self, test_user, live_order_with_exchange_data):
        """Test API returns exchange_order_id"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        live_order = next((o for o in orders if o.get("exchange_order_id") is not None), None)
        assert live_order is not None

        assert live_order["exchange_order_id"] == "HYPER-12345"

    def test_order_includes_exchange(self, test_user, live_order_with_exchange_data):
        """Test API returns exchange field"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        live_order = next((o for o in orders if o.get("exchange") is not None), None)
        assert live_order is not None

        assert live_order["exchange"] == "HYPERLIQUID"

    def test_order_includes_actual_fill_price(self, test_user, live_order_with_exchange_data):
        """Test API returns actual_fill_price"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        live_order = next((o for o in orders if o.get("actual_fill_price") is not None), None)
        assert live_order is not None

        assert float(live_order["actual_fill_price"]) == pytest.approx(3001.50, rel=1e-2)

    def test_live_order_has_all_phase2_fields(self, test_user, live_order_with_exchange_data):
        """Test live order has all Phase 2 fields populated"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        live_order = next((o for o in orders if o.get("exchange") == "HYPERLIQUID"), None)
        assert live_order is not None

        # All Phase 2 fields should be present
        assert live_order["exchange_order_id"] == "HYPER-12345"
        assert live_order["exchange"] == "HYPERLIQUID"
        assert live_order["actual_fill_price"] is not None


class TestOrderResponseStructure:
    """Test order API response structure"""

    def test_response_includes_all_required_fields(self, test_user, paper_order_with_slippage):
        """Test response includes all expected fields"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()
        order = orders[0]

        # Core fields
        assert "id" in order
        assert "order_no" in order
        assert "user_id" in order
        assert "symbol" in order
        assert "name" in order
        assert "market" in order
        assert "side" in order
        assert "order_type" in order
        assert "quantity" in order
        assert "filled_quantity" in order
        assert "status" in order

        # Phase 1 fields
        assert "slippage" in order
        assert "rejection_reason" in order

        # Phase 2 fields
        assert "exchange_order_id" in order
        assert "exchange" in order
        assert "actual_fill_price" in order

    def test_field_types_are_correct(self, test_user, live_order_with_exchange_data):
        """Test all fields have correct data types"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()
        order = orders[0]

        # Integer fields
        assert isinstance(order["id"], int)
        assert isinstance(order["user_id"], int)

        # String fields
        assert isinstance(order["order_no"], str)
        assert isinstance(order["symbol"], str)
        assert isinstance(order["side"], str)
        assert isinstance(order["status"], str)

        # Optional numeric fields
        if order["slippage"] is not None:
            assert isinstance(order["slippage"], (int, float))

        if order["actual_fill_price"] is not None:
            assert isinstance(order["actual_fill_price"], (int, float))


class TestBackwardCompatibility:
    """Test backward compatibility with legacy orders"""

    def test_legacy_order_without_phase_fields(self, test_account):
        """Test order without Phase 1/2 fields returns null values"""
        db = TestingSessionLocal()
        try:
            # Create legacy order without Phase 1/2 fields
            legacy_order = Order(
                version="v1",
                account_id=test_account.id,
                order_no="ORD-LEGACY-001",
                symbol="SOL",
                name="Solana",
                market="CRYPTO",
                side="BUY",
                order_type="MARKET",
                price=Decimal("100.00"),
                quantity=Decimal("50.0"),
                filled_quantity=Decimal("50.0"),
                status="FILLED"
                # No slippage, rejection_reason, exchange fields
            )
            db.add(legacy_order)
            db.commit()

            response = client.get(f"/api/orders/user/{test_account.user_id}")

            assert response.status_code == 200
            orders = response.json()

            legacy = next((o for o in orders if o["order_no"] == "ORD-LEGACY-001"), None)
            assert legacy is not None

            # Phase 1/2 fields should be null but present
            assert "slippage" in legacy
            assert legacy["slippage"] is None

            assert "rejection_reason" in legacy
            assert legacy["rejection_reason"] is None

            assert "exchange_order_id" in legacy
            assert legacy["exchange_order_id"] is None

            assert "exchange" in legacy
            assert legacy["exchange"] is None

            assert "actual_fill_price" in legacy
            assert legacy["actual_fill_price"] is None

        finally:
            db.close()

    def test_old_clients_dont_break(self, test_user, paper_order_with_slippage):
        """Test existing API clients still work with new fields"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        # Old fields still present
        order = orders[0]
        assert order["order_no"] == "ORD-PAPER-001"
        assert order["symbol"] == "BTC"
        assert order["status"] == "FILLED"

        # New fields are additional
        assert "slippage" in order
        assert "exchange_order_id" in order


class TestMultipleOrders:
    """Test API with multiple orders"""

    def test_list_mixed_paper_and_live_orders(
        self,
        test_user,
        paper_order_with_slippage,
        live_order_with_exchange_data
    ):
        """Test listing both paper and live orders"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        assert len(orders) >= 2

        # Find paper order
        paper = next((o for o in orders if o["order_no"] == "ORD-PAPER-001"), None)
        assert paper is not None
        assert paper["slippage"] is not None
        assert paper["exchange_order_id"] is None  # Paper order has no exchange ID

        # Find live order
        live = next((o for o in orders if o["order_no"] == "ORD-LIVE-001"), None)
        assert live is not None
        assert live["exchange_order_id"] == "HYPER-12345"
        assert live["exchange"] == "HYPERLIQUID"

    def test_each_order_has_independent_phase_fields(
        self,
        test_user,
        paper_order_with_slippage,
        rejected_order,
        live_order_with_exchange_data
    ):
        """Test each order maintains its own Phase 1/2 data"""
        response = client.get(f"/api/orders/user/{test_user.id}")

        assert response.status_code == 200
        orders = response.json()

        # Paper order has slippage but no exchange data
        paper = next((o for o in orders if o["order_no"] == "ORD-PAPER-001"), None)
        assert paper["slippage"] is not None
        assert paper["exchange"] is None

        # Rejected order has rejection_reason but no slippage
        rejected = next((o for o in orders if o["order_no"] == "ORD-REJECTED-001"), None)
        assert rejected["rejection_reason"] is not None
        assert rejected["slippage"] is None

        # Live order has all Phase 2 fields
        live = next((o for o in orders if o["order_no"] == "ORD-LIVE-001"), None)
        assert live["exchange_order_id"] is not None
        assert live["exchange"] == "HYPERLIQUID"
        assert live["actual_fill_price"] is not None


class TestOrderFiltering:
    """Test order filtering functionality"""

    def test_filter_by_status(self, test_user, paper_order_with_slippage, rejected_order):
        """Test filtering orders by status includes Phase 1/2 fields"""
        # Get only filled orders
        response = client.get(f"/api/orders/user/{test_user.id}?status=FILLED")

        assert response.status_code == 200
        orders = response.json()

        # Should only get filled orders
        for order in orders:
            assert order["status"] == "FILLED"
            # Should still have Phase 1/2 fields
            assert "slippage" in order
            assert "exchange_order_id" in order

        # Get only rejected orders
        response = client.get(f"/api/orders/user/{test_user.id}?status=REJECTED")

        assert response.status_code == 200
        orders = response.json()

        # Should only get rejected orders
        for order in orders:
            assert order["status"] == "REJECTED"
            assert "rejection_reason" in order


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
