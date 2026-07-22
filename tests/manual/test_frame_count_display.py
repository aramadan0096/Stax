# -*- coding: utf-8 -*-
"""
Test frame count display logic
"""

# Simulate the frame count parsing logic
def parse_frame_count(frame_range):
    """Parse frame_range string and return frame count."""
    frame_display = ''
    if frame_range and '-' in str(frame_range):
        try:
            parts = str(frame_range).split('-')
            if len(parts) == 2:
                start_frame = int(parts[0])
                end_frame = int(parts[1])
                frame_count = end_frame - start_frame + 1
                frame_display = str(frame_count)
            else:
                # Malformed range, display as-is
                frame_display = str(frame_range)
        except (ValueError, IndexError):
            frame_display = str(frame_range)
    elif frame_range:
        frame_display = str(frame_range)
    return frame_display


# Test cases
test_cases = [
    ('1-7', '7'),
    ('1-100', '100'),
    ('0-23', '24'),
    ('1001-1050', '50'),
    (None, ''),
    ('', ''),
    ('invalid', 'invalid'),
    ('1-2-3', '1-2-3'),  # malformed
]

print("="*60)
print("FRAME COUNT DISPLAY TEST")
print("="*60)

all_passed = True
for input_val, expected in test_cases:
    result = parse_frame_count(input_val)
    status = "✓ PASS" if result == expected else "✗ FAIL"
    if result != expected:
        all_passed = False
    print("{}: '{}' -> '{}' (expected: '{}')".format(status, input_val, result, expected))

print("="*60)
if all_passed:
    print("✓ ALL TESTS PASSED")
else:
    print("✗ SOME TESTS FAILED")
print("="*60)
