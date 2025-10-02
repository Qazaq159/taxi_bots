#!/usr/bin/env python3
"""
Test script to verify Django logging configuration
"""
import sys
import os

# Add the project root and taxi_bot directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'taxi_bot'))

# Set Django settings before any other imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'taxi_bot.settings')

# Initialize Django
import django
django.setup()

import logging

def test_logging():
    """Test the logging configuration"""
    print("Testing Django logging configuration...")

    # Test different loggers
    loggers_to_test = [
        'taxi_bot.bot_service.driver',
        'taxi_bot.bot_service.driver.menu_handler',
        'taxi_bot.bot_service.driver.ride_management',
        'api.services',
        'django'
    ]

    for logger_name in loggers_to_test:
        logger = logging.getLogger(logger_name)
        print(f"\nTesting logger: {logger_name}")
        print(f"  Logger level: {logger.level}")
        print(f"  Effective level: {logger.getEffectiveLevel()}")
        print(f"  Handlers: {[h.__class__.__name__ for h in logger.handlers]}")
        print(f"  Parent: {logger.parent}")

        # Test a log message
        logger.info(f"Test message from {logger_name}")

    print("\n" + "="*50)
    print("Logging test complete!")
    print("Check the terminal output and log files in logs/ directory")

if __name__ == '__main__':
    test_logging()
