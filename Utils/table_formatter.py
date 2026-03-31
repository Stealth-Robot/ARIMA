"""
Formats all Markdown tables in a file so that:
- Every cell has at least 1 space of padding on each side.
- The longest cell content in each column has exactly 1 space on each side.
- All vertical pipes align within each table.

Usage: python table_formatter.py <file.md>
"""

import re
import sys


def format_table(table_text):
    lines = table_text.strip().split('\n')

    rows = []
    sep_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if all(re.match(r'^-+$', c) for c in cells):
                sep_idx = i
                rows.append(None)
            else:
                rows.append(cells)
        else:
            break

    if sep_idx is None or len(rows) < 3:
        return table_text

    num_cols = len(rows[0])

    for i, row in enumerate(rows):
        if row is not None:
            if len(row) < num_cols:
                row.extend([''] * (num_cols - len(row)))
            elif len(row) > num_cols:
                rows[i] = row[:num_cols]

    col_widths = []
    for col in range(num_cols):
        max_len = 0
        for row in rows:
            if row is not None and col < len(row):
                max_len = max(max_len, len(row[col]))
        col_widths.append(max_len)

    result_lines = []
    for row in rows:
        if row is None:
            parts = ['|']
            for w in col_widths:
                parts.append('-' * (w + 2) + '|')
            result_lines.append(''.join(parts))
        else:
            parts = ['|']
            for col_idx, cell in enumerate(row[:num_cols]):
                w = col_widths[col_idx]
                parts.append(' ' + cell.ljust(w) + ' |')
            result_lines.append(''.join(parts))

    return '\n'.join(result_lines)


def replace_tables(text):
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        if (lines[i].strip().startswith('|')
                and i + 1 < len(lines)
                and lines[i + 1].strip().startswith('|')):
            table_lines = []
            j = i
            while (j < len(lines)
                   and lines[j].strip().startswith('|')
                   and lines[j].strip().endswith('|')):
                table_lines.append(lines[j])
                j += 1

            if len(table_lines) >= 3:
                result.append(format_table('\n'.join(table_lines)))
                i = j
            else:
                result.append(lines[i])
                i += 1
        else:
            result.append(lines[i])
            i += 1

    return '\n'.join(result)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <file.md>")
        sys.exit(1)

    filepath = sys.argv[1]

    with open(filepath, 'r') as f:
        content = f.read()

    formatted = replace_tables(content)

    with open(filepath, 'w') as f:
        f.write(formatted)

    print(f"Formatted tables in {filepath}")


if __name__ == '__main__':
    main()
