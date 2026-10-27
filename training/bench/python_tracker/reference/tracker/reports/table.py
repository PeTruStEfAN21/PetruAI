"""Plain text tables."""


def render_table(headers, rows) -> str:
    """Columns two spaces apart, a dashed rule under the header; ints right-aligned."""
    table = [list(headers), *(list(row) for row in rows)]
    widths = [max(len(str(row[col])) for row in table) for col in range(len(headers))]

    def line(row):
        cells = [
            str(value).rjust(width) if isinstance(value, int) else str(value).ljust(width)
            for value, width in zip(row, widths)
        ]
        return "  ".join(cells).rstrip()

    rule = "  ".join("-" * width for width in widths)
    return "\n".join([line(table[0]), rule, *(line(row) for row in table[1:])])
