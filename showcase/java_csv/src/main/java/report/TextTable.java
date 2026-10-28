package report;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class TextTable {

    public static String render(Table table) {
        List<List<String>> rows = new ArrayList<>();
        for (int i = 0; i < table.rowCount(); i++) {
            rows.add(table.row(i));
        }

        List<String> columns = table.columns();
        int numColumns = columns.size();

        // Calculate column widths
        int[] colWidths = new int[numColumns];
        for (int j = 0; j < numColumns; j++) {
            int maxWidth = columns.get(j).length();
            for (List<String> row : rows) {
                if (j < row.size()) {
                    maxWidth = Math.max(maxWidth, row.get(j).length());
                }
            }
            colWidths[j] = maxWidth;
        }

        // Determine alignment for each column
        boolean[] rightAlign = new boolean[numColumns];
        for (int j = 0; j < numColumns; j++) {
            rightAlign[j] = isAllNumericColumn(j, rows);
        }

        // Build all lines
        List<String> lines = new ArrayList<>();

        // Header row
        lines.add(buildRow(columns, colWidths, rightAlign));

        // Separator row
        lines.add(buildSeparator(colWidths));

        // Data rows
        for (int i = 1; i < rows.size(); i++) {
            lines.add(buildRow(rows.get(i), colWidths, rightAlign));
        }

        return String.join("\n", lines);
    }

    private static String buildRow(List<String> cells, int[] colWidths, boolean[] rightAlign) {
        StringBuilder sb = new StringBuilder();
        for (int j = 0; j < cells.size(); j++) {
            if (j > 0) sb.append(" | ");
            String value = j < cells.size() ? cells.get(j) : "";
            sb.append(formatCell(value, colWidths[j], rightAlign[j]));
        }
        return sb.toString();
    }

    private static String buildSeparator(int[] colWidths) {
        StringBuilder sb = new StringBuilder();
        for (int j = 0; j < colWidths.length; j++) {
            if (j > 0) sb.append("-+-");
            sb.append("-".repeat(colWidths[j]));
        }
        return sb.toString();
    }

    private static boolean isAllNumericColumn(int columnIdx, List<List<String>> rows) {
        for (List<String> row : rows) {
            if (columnIdx >= row.size()) {
                return false;
            }
            String value = row.get(columnIdx);
            if (value.isEmpty()) {
                return false;
            }
            try {
                new BigDecimal(value);
            } catch (NumberFormatException e) {
                return false;
            }
        }
        return true;
    }

    private static String formatCell(String value, int width, boolean rightAlign) {
        if (value == null) value = "";
        int actualWidth = value.length();
        if (actualWidth < width) {
            if (rightAlign) {
                return " ".repeat(width - actualWidth) + value;
            } else {
                return value + " ".repeat(width - actualWidth);
            }
        }
        return value;
    }
}
