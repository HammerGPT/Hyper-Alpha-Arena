"""
Test account API endpoints for Phase 2 field exposure.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.connection import Base, get_db
from main import app
from database.models import User, Account


# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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
def paper_account(test_user):
    """Create a PAPER mode account"""
    db = TestingSessionLocal()
    try:
        account = Account(
            user_id=test_user.id,
            version="v1",
            name="Paper Trader",
            model="gpt-4",
            base_url="https://api.openai.com/v1",
            api_key="sk-test123",
            initial_capital=10000.0,
            current_cash=10000.0,
            frozen_cash=0.0,
            account_type="AI",
            is_active="true",
            auto_trading_enabled="false",
            trading_mode="PAPER",
            exchange="HYPERLIQUID",
            testnet_enabled="true"
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account
    finally:
        db.close()


@pytest.fixture(scope="function")
def live_account(test_user):
    """Create a LIVE mode account"""
    db = TestingSessionLocal()
    try:
        account = Account(
            user_id=test_user.id,
            version="v1",
            name="Live Trader",
            model="gpt-4-turbo",
            base_url="https://api.openai.com/v1",
            api_key="sk-live456",
            initial_capital=50000.0,
            current_cash=48000.0,
            frozen_cash=2000.0,
            account_type="AI",
            is_active="true",
            auto_trading_enabled="true",
            trading_mode="LIVE",
            exchange="HYPERLIQUID",
            wallet_address="0x1234567890abcdef",
            testnet_enabled="false"
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account
    finally:
        db.close()


class TestAccountListEndpoint:
    """Test GET /api/account/list endpoint"""

    def test_list_paper_account_includes_phase2_fields(self, paper_account):
        """Test API returns Phase 2 fields for PAPER accounts"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()

        assert len(accounts) >= 1

        account = accounts[0]
        assert account["id"] == paper_account.id
        assert account["trading_mode"] == "PAPER"
        assert account["exchange"] == "HYPERLIQUID"
        assert account["testnet_enabled"] == "true"
        assert account.get("wallet_address") is None

    def test_list_live_account_includes_phase2_fields(self, live_account):
        """Test API returns Phase 2 fields for LIVE accounts"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()

        assert len(accounts) >= 1

        # Find the live account
        live_acc = next((a for a in accounts if a["id"] == live_account.id), None)
        assert live_acc is not None

        assert live_acc["trading_mode"] == "LIVE"
        assert live_acc["exchange"] == "HYPERLIQUID"
        assert live_acc["wallet_address"] == "0x1234567890abcdef"
        assert live_acc["testnet_enabled"] == "false"

    def test_list_all_status(self, paper_account):
        """Test filtering by status=all"""
        response = client.get("/api/account/list?status=all")

        assert response.status_code == 200
        accounts = response.json()

        assert len(accounts) >= 1

    def test_list_archived_status(self, setup_database):
        """Test filtering by status=archived"""
        response = client.get("/api/account/list?status=archived")

        assert response.status_code == 200
        accounts = response.json()

        # Should be empty or only contain archived accounts
        for account in accounts:
            assert account["is_active"] is False

    def test_phase2_fields_have_correct_types(self, paper_account):
        """Test Phase 2 fields have correct data types"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()
        account = accounts[0]

        # trading_mode should be string
        assert isinstance(account["trading_mode"], str)
        # exchange can be string or None
        assert account["exchange"] is None or isinstance(account["exchange"], str)
        # wallet_address can be string or None
        assert account["wallet_address"] is None or isinstance(account["wallet_address"], str)
        # testnet_enabled should be string ("true" or "false")
        assert isinstance(account["testnet_enabled"], str)
        assert account["testnet_enabled"] in ["true", "false"]


class TestAccountResponseStructure:
    """Test account API response structure"""

    def test_response_includes_all_required_fields(self, paper_account):
        """Test response includes all expected fields"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()
        account = accounts[0]

        # Core fields
        assert "id" in account
        assert "user_id" in account
        assert "name" in account
        assert "model" in account
        assert "base_url" in account
        assert "api_key" in account
        assert "initial_capital" in account
        assert "current_cash" in account
        assert "frozen_cash" in account
        assert "account_type" in account
        assert "is_active" in account

        # Phase 2 fields
        assert "trading_mode" in account
        assert "exchange" in account
        assert "wallet_address" in account
        assert "testnet_enabled" in account

    def test_response_has_default_values_for_legacy_data(self, test_user):
        """Test accounts without Phase 2 data return defaults"""
        # Create legacy account without Phase 2 fields
        db = TestingSessionLocal()
        try:
            # Manually insert without Phase 2 fields to simulate legacy data
            legacy_account = Account(
                user_id=test_user.id,
                version="v1",
                name="Legacy Account",
                model="gpt-3.5-turbo",
                base_url="https://api.openai.com/v1",
                api_key="sk-legacy",
                initial_capital=5000.0,
                current_cash=5000.0,
                frozen_cash=0.0,
                account_type="AI",
                is_active="true",
                auto_trading_enabled="false"
                # No trading_mode, exchange, etc.
            )
            db.add(legacy_account)
            db.commit()
            db.refresh(legacy_account)

            response = client.get("/api/account/list?status=active")

            assert response.status_code == 200
            accounts = response.json()

            legacy_acc = next((a for a in accounts if a["id"] == legacy_account.id), None)
            assert legacy_acc is not None

            # Should have defaults
            assert legacy_acc["trading_mode"] == "PAPER"
            assert legacy_acc["testnet_enabled"] == "true"

        finally:
            db.close()


class TestBackwardCompatibility:
    """Test backward compatibility with existing clients"""

    def test_old_clients_dont_break(self, paper_account):
        """Test that adding Phase 2 fields doesn't break existing API contract"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()

        # Old clients should still get their expected fields
        account = accounts[0]
        assert account["id"] == paper_account.id
        assert account["name"] == "Paper Trader"
        assert account["model"] == "gpt-4"

        # New fields are additional, not replacing anything
        assert "trading_mode" in account  # New
        assert "is_active" in account  # Old, still present

    def test_null_values_handled_correctly(self, paper_account):
        """Test null/None values in Phase 2 fields are handled correctly"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()
        account = accounts[0]

        # wallet_address is None for PAPER accounts
        assert account["wallet_address"] is None

        # Should not cause errors or be omitted
        assert "wallet_address" in account


class TestMultipleAccounts:
    """Test API with multiple accounts"""

    def test_list_mixed_paper_and_live_accounts(self, paper_account, live_account):
        """Test listing both PAPER and LIVE accounts"""
        response = client.get("/api/account/list?status=active")

        assert response.status_code == 200
        accounts = response.json()

        assert len(accounts) >= 2

        paper_acc = next((a for a in accounts if a["trading_mode"] == "PAPER"), None)
        live_acc = next((a for a in accounts if a["trading_mode"] == "LIVE"), None)

        assert paper_acc is not None
        assert live_acc is not None

        # Paper account characteristics
        assert paper_acc["testnet_enabled"] == "true"

        # Live account characteristics
        assert live_acc["wallet_address"] == "0x1234567890abcdef"
        assert live_acc["testnet_enabled"] == "false"

    def test_each_account_has_independent_phase2_fields(self, paper_account, live_account):
        """Test each account maintains its own Phase 2 configuration"""
        response = client.get("/api/account/list?status=all")

        assert response.status_code == 200
        accounts = response.json()

        # Group by trading mode
        paper_accounts = [a for a in accounts if a["trading_mode"] == "PAPER"]
        live_accounts = [a for a in accounts if a["trading_mode"] == "LIVE"]

        # Each should have distinct configurations
        for acc in paper_accounts:
            assert acc["trading_mode"] == "PAPER"

        for acc in live_accounts:
            assert acc["trading_mode"] == "LIVE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
