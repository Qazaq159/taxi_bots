#!/usr/bin/env python3
"""
Test script to verify rating callback pattern matching
"""
import re

def test_callback_pattern():
    """Test the callback pattern matching"""
    pattern = r'^rate_passenger_\d+_.*$'

    test_cases = [
        'rate_passenger_5_e6878856-5c5a-441f-a736-67010b0562c8',
        'rate_passenger_4_12345678-abcd-efgh-ijkl-123456789012',
        'rate_passenger_3_test-uuid-123',
        'invalid_callback_data',
        'rate_driver_5_uuid'
    ]

    print("Testing callback pattern matching:")
    print(f"Pattern: {pattern}")
    print()

    for test_case in test_cases:
        match = re.match(pattern, test_case)
        result = "✅ MATCH" if match else "❌ NO MATCH"
        print(f"{result}: {test_case}")

    print()
    print("Expected: First 3 should match, last 2 should not match")

if __name__ == '__main__':
    test_callback_pattern()
