#!/usr/bin/env python3
"""
Test and fix logger configuration for trading_strategy
"""
import logging

# Get the logger
logger = logging.getLogger("services.trading_strategy")

print("=" * 80)
print("Logger Configuration Test")
print("=" * 80)

print(f"\nLogger name: {logger.name}")
print(f"Logger level: {logger.level} ({logging.getLevelName(logger.level)})")
print(f"Logger effective level: {logger.getEffectiveLevel()} ({logging.getLevelName(logger.getEffectiveLevel())})")
print(f"Logger handlers: {logger.handlers}")
print(f"Logger propagate: {logger.propagate}")

# Get parent loggers
current = logger
print("\nLogger hierarchy:")
while current:
    print(f"  {current.name}: level={current.level} ({logging.getLevelName(current.level)}), handlers={len(current.handlers)}")
    current = current.parent if hasattr(current, 'parent') else None

# Test logging
print("\nTesting log output:")
print("  Calling logger.debug('TEST DEBUG')...")
logger.debug("TEST DEBUG - This is a debug message")

print("  Calling logger.info('TEST INFO')...")
logger.info("TEST INFO - This is an info message")

print("  Calling logger.warning('TEST WARNING')...")
logger.warning("TEST WARNING - This is a warning message")

print("  Calling logger.error('TEST ERROR')...")
logger.error("TEST ERROR - This is an error message")

print("\n" + "=" * 80)
print("If you don't see log messages above, logger level needs to be adjusted")
print("=" * 80)

# Force set level to DEBUG
print("\nForcing logger level to DEBUG...")
logger.setLevel(logging.DEBUG)

# Also set root logger
logging.getLogger().setLevel(logging.DEBUG)

print(f"New logger level: {logger.level} ({logging.getLevelName(logger.level)})")
print(f"New effective level: {logger.getEffectiveLevel()} ({logging.getLevelName(logger.getEffectiveLevel())})")

print("\nTesting again:")
logger.debug("TEST DEBUG AFTER FIX")
logger.info("TEST INFO AFTER FIX")
logger.warning("TEST WARNING AFTER FIX")
logger.error("TEST ERROR AFTER FIX")

print("\n" + "=" * 80)
