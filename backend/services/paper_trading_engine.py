"""
Enhanced paper trading engine with realistic simulations

This module simulates realistic trading conditions without requiring exchange API credentials:
- Slippage simulation (0.01-0.1% based on order size)
- Latency simulation (50-200ms execution delay)
- Partial fills for large orders
- Order rejections based on liquidity constraints
- Market impact for large orders

All simulations use real market data from public CCXT endpoints.
"""

import random
import time
import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Result of paper trading simulation"""
    status: str  # "FILLED", "PARTIALLY_FILLED", "REJECTED"
    execution_price: Optional[Decimal] = None
    filled_quantity: Optional[Decimal] = None
    slippage: Optional[Decimal] = None
    rejection_reason: Optional[str] = None


class PaperTradingEngine:
    """
    Enhanced paper trading engine with realistic simulations

    Configuration parameters can be adjusted based on market conditions.
    All calculations use Decimal for precision.
    """

    # Slippage configuration (basis points)
    MIN_SLIPPAGE_BPS = 1    # 0.01% for small orders
    MAX_SLIPPAGE_BPS = 10   # 0.1% for large orders
    SLIPPAGE_SIZE_THRESHOLD = 10000  # $10k order triggers higher slippage

    # Latency configuration (milliseconds)
    MIN_LATENCY_MS = 50
    MAX_LATENCY_MS = 200

    # Liquidity constraints
    MAX_ORDER_VALUE_USD = 100000  # Reject orders larger than $100k
    PARTIAL_FILL_THRESHOLD_USD = 10000  # Orders > $10k may get partial fills
    PARTIAL_FILL_PROBABILITY = 0.1  # 10% chance for large orders
    MIN_PARTIAL_FILL_PCT = 0.5  # Minimum 50% fill
    MAX_PARTIAL_FILL_PCT = 0.9  # Maximum 90% fill

    # General rejection probability
    BASE_REJECTION_PROBABILITY = 0.02  # 2% base rejection rate

    def __init__(self):
        """Initialize paper trading engine"""
        random.seed()  # Ensure randomness

    def simulate_order_execution(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        current_price: Decimal,
        limit_price: Optional[Decimal] = None
    ) -> SimulationResult:
        """
        Simulate realistic order execution

        Args:
            symbol: Trading symbol (e.g., 'BTC')
            side: Order side ('BUY' or 'SELL')
            order_type: Order type ('MARKET' or 'LIMIT')
            quantity: Order quantity
            current_price: Current market price
            limit_price: Limit price for limit orders

        Returns:
            SimulationResult with execution details or rejection reason
        """
        # Calculate order value
        order_value = float(current_price * quantity)

        # Step 1: Check liquidity constraints
        if order_value > self.MAX_ORDER_VALUE_USD:
            logger.info(f"Order rejected: size ${order_value:.2f} exceeds liquidity limit ${self.MAX_ORDER_VALUE_USD}")
            return SimulationResult(
                status="REJECTED",
                rejection_reason=f"Order size ${order_value:.2f} exceeds maximum ${self.MAX_ORDER_VALUE_USD}"
            )

        # Step 2: Simulate random rejection (exchange errors, rate limits, etc.)
        if random.random() < self.BASE_REJECTION_PROBABILITY:
            rejection_reasons = [
                "Simulated exchange error (503 Service Unavailable)",
                "Simulated rate limit exceeded",
                "Simulated symbol temporarily suspended",
                "Simulated insufficient exchange liquidity"
            ]
            reason = random.choice(rejection_reasons)
            logger.info(f"Order randomly rejected: {reason}")
            return SimulationResult(
                status="REJECTED",
                rejection_reason=reason
            )

        # Step 3: Simulate execution latency
        self._simulate_latency()

        # Step 4: Calculate slippage
        slippage_bps = self._calculate_slippage(order_value)
        slippage_multiplier = Decimal(str(1 + slippage_bps / 10000))

        # Apply slippage direction based on side
        if side == "BUY":
            # Buying: price increases (unfavorable slippage)
            execution_price = current_price * slippage_multiplier
        else:
            # Selling: price decreases (unfavorable slippage)
            execution_price = current_price / slippage_multiplier

        # Step 5: Check for partial fills
        filled_quantity = quantity
        status = "FILLED"

        if order_value > self.PARTIAL_FILL_THRESHOLD_USD:
            if random.random() < self.PARTIAL_FILL_PROBABILITY:
                # Partial fill occurs
                fill_pct = random.uniform(self.MIN_PARTIAL_FILL_PCT, self.MAX_PARTIAL_FILL_PCT)
                filled_quantity = quantity * Decimal(str(fill_pct))
                status = "PARTIALLY_FILLED"
                logger.info(f"Partial fill simulation: {fill_pct*100:.1f}% of order filled")

        # Calculate final slippage percentage for reporting
        slippage_pct = abs(execution_price - current_price) / current_price

        logger.info(
            f"Paper trade executed: {side} {float(filled_quantity):.6f} {symbol} "
            f"@ ${float(execution_price):.2f} (slippage: {float(slippage_pct)*100:.4f}%)"
        )

        return SimulationResult(
            status=status,
            execution_price=execution_price,
            filled_quantity=filled_quantity,
            slippage=slippage_pct
        )

    def _calculate_slippage(self, order_value: float) -> float:
        """
        Calculate slippage in basis points based on order size

        Larger orders experience higher slippage due to market impact.

        Args:
            order_value: Order value in USD

        Returns:
            Slippage in basis points (1 bp = 0.01%)
        """
        if order_value < self.SLIPPAGE_SIZE_THRESHOLD:
            # Small order: minimal slippage
            return random.uniform(self.MIN_SLIPPAGE_BPS, self.MIN_SLIPPAGE_BPS * 2)
        else:
            # Large order: higher slippage
            # Linear interpolation based on size
            size_factor = min(order_value / self.MAX_ORDER_VALUE_USD, 1.0)
            max_slippage = self.MIN_SLIPPAGE_BPS + (self.MAX_SLIPPAGE_BPS - self.MIN_SLIPPAGE_BPS) * size_factor
            return random.uniform(self.MIN_SLIPPAGE_BPS, max_slippage)

    def _simulate_latency(self):
        """
        Simulate network and exchange processing latency

        Adds random delay between MIN_LATENCY_MS and MAX_LATENCY_MS to simulate
        real-world order execution time.
        """
        latency_seconds = random.uniform(
            self.MIN_LATENCY_MS / 1000,
            self.MAX_LATENCY_MS / 1000
        )
        time.sleep(latency_seconds)
        logger.debug(f"Simulated execution latency: {latency_seconds*1000:.0f}ms")

    def validate_order_size(self, symbol: str, quantity: Decimal, current_price: Decimal) -> Tuple[bool, Optional[str]]:
        """
        Validate order size against liquidity constraints

        Args:
            symbol: Trading symbol
            quantity: Order quantity
            current_price: Current market price

        Returns:
            Tuple of (is_valid, error_message)
        """
        order_value = float(current_price * quantity)

        if order_value > self.MAX_ORDER_VALUE_USD:
            return False, f"Order size ${order_value:.2f} exceeds maximum ${self.MAX_ORDER_VALUE_USD}"

        # Check minimum order size ($1)
        if order_value < 1.0:
            return False, f"Order size ${order_value:.2f} below minimum $1.00"

        return True, None

    def estimate_slippage(self, order_value: float) -> Dict[str, float]:
        """
        Estimate slippage range for a given order size

        Useful for displaying estimated costs to users before order placement.

        Args:
            order_value: Order value in USD

        Returns:
            Dict with min_slippage_pct, max_slippage_pct, avg_slippage_pct
        """
        if order_value < self.SLIPPAGE_SIZE_THRESHOLD:
            min_bps = self.MIN_SLIPPAGE_BPS
            max_bps = self.MIN_SLIPPAGE_BPS * 2
        else:
            size_factor = min(order_value / self.MAX_ORDER_VALUE_USD, 1.0)
            max_bps = self.MIN_SLIPPAGE_BPS + (self.MAX_SLIPPAGE_BPS - self.MIN_SLIPPAGE_BPS) * size_factor
            min_bps = self.MIN_SLIPPAGE_BPS

        return {
            "min_slippage_pct": min_bps / 10000,
            "max_slippage_pct": max_bps / 10000,
            "avg_slippage_pct": (min_bps + max_bps) / 2 / 10000,
            "order_value": order_value
        }


# Global instance for use across the application
paper_trading_engine = PaperTradingEngine()
