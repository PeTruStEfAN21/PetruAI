package report;

import java.util.List;

public class CsvWriter {

    public static String write(Table table) {
        List<String> columns = table.columns();
        StringBuilder sb = new StringBuilder();

        // Write header row
        for (int i = 0; i < columns.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append(quoteField(columns.get(i)));
        }
        sb.append('\n');

        // Write data rows
        for (int i = 0; i < table.rowCount(); i++) {
            List<String> row = table.row(i);
            for (int j = 0; j < row.size(); j++) {
                if (j > 0) sb.append(',');
                sb.append(quoteField(row.get(j)));
            }
            sb.append('\n');
        }

        return sb.toString();
    }

    private static String quoteField(String value) {
        // Check if quoting is needed: contains comma, double quote, newline, or leading/trailing space
        if (value.contains(",") || value.contains("\"") || value.contains("\n")
                || value.contains("\r") || (value.length() > 0 && (value.charAt(0) == ' ' || value.charAt(value.length() - 1) == ' '))) {
            StringBuilder sb = new StringBuilder();
            sb.append('"');
            for (int i = 0; i < value.length(); i++) {
                char c = value.charAt(i);
                if (c == '"') {
                    sb.append('"').append('"');
                } else {
                    sb.append(c);
                }
            }
            sb.append('"');
            return sb.toString();
        }
        return value;
    }
}
