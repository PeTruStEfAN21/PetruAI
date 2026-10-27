package report;

import java.util.ArrayList;
import java.util.List;

/** A plain-text table: numeric columns right-aligned, others left-aligned, no trailing spaces. */
public final class TextTable {
    private TextTable() {}

    public static String render(Table table) {
        List<String> columns = table.columns();
        int n = columns.size();
        int[] widths = new int[n];
        boolean[] numeric = new boolean[n];
        for (int c = 0; c < n; c++) {
            List<String> values = table.column(columns.get(c));
            widths[c] = columns.get(c).length();
            numeric[c] = !values.isEmpty();
            for (String v : values) {
                widths[c] = Math.max(widths[c], v.length());
                numeric[c] &= Numbers.isNumber(v);
            }
        }
        List<String> lines = new ArrayList<>();
        lines.add(line(columns, widths, numeric));
        List<String> rule = new ArrayList<>();
        for (int w : widths) {
            rule.add("-".repeat(w));
        }
        lines.add(String.join("-+-", rule));
        for (int r = 0; r < table.rowCount(); r++) {
            lines.add(line(table.row(r), widths, numeric));
        }
        return String.join("\n", lines);
    }

    private static String line(List<String> cells, int[] widths, boolean[] numeric) {
        List<String> padded = new ArrayList<>();
        for (int c = 0; c < cells.size(); c++) {
            String format = numeric[c] ? "%" + widths[c] + "s" : "%-" + widths[c] + "s";
            padded.add(String.format(format, cells.get(c)));
        }
        return String.join(" | ", padded).stripTrailing();
    }
}
