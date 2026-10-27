package report;

import java.util.List;
import java.util.stream.Collectors;

public final class CsvWriter {
    private CsvWriter() {}

    /** Header and rows, LF line ends, a final newline; fields quoted only when needed. */
    public static String write(Table table) {
        StringBuilder out = new StringBuilder();
        out.append(line(table.columns()));
        for (int r = 0; r < table.rowCount(); r++) {
            out.append(line(table.row(r)));
        }
        return out.toString();
    }

    private static String line(List<String> fields) {
        return fields.stream().map(CsvWriter::quote).collect(Collectors.joining(",")) + "\n";
    }

    static String quote(String field) {
        boolean needs = field.contains(",") || field.contains("\"") || field.contains("\n") || field.contains("\r")
            || !field.equals(field.strip());
        return needs ? "\"" + field.replace("\"", "\"\"") + "\"" : field;
    }
}
