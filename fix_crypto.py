#!/usr/bin/env python3
"""Fix the specific indentation issue in crypto.py"""

with open('src/crypto.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix lines 81-83 (0-indexed: 80-82)
# The decompress function body has incorrect indentation
fixed_lines = []
for i, line in enumerate(lines):
    if i == 80:  # Line 81: if statement
        fixed_lines.append('    if data[:2] == _GZIP_MAGIC:\n')
    elif i == 81:  # Line 82: return inside if
        fixed_lines.append('        return gzip.decompress(data)\n')
    elif i == 82:  # Line 83: return outside if
        fixed_lines.append('    return data # Not compressed — pass through (backward compat)\n')
    else:
        fixed_lines.append(line)

with open('src/crypto.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('✅ Fixed crypto.py indentation')
