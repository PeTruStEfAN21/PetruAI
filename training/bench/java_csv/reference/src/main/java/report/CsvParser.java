package report;

import java.util.ArrayList;
import java.util.List;

/** RFC 4180 style CSV: commas, CRLF or LF, double quotes with "" inside, line breaks inside quotes. */
public final class CsvParser {
    private CsvParser() {}

    public static List<List<String>> parse(String text) {
        return parseWithLines(text).rows();
    }

    /** The rows plus the line on which each row starts, for error messages. */
    record Parsed(List<List<String>> rows, List<Integer> lines) {}

    static Parsed parseWithLines(String text) {
        List<List<String>> rows = new ArrayList<>();
        List<Integer> lines = new ArrayList<>();
        List<String> row = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        int line = 1;
        int rowLine = 1;
        int i = 0;
        boolean rowStarted = false;
        while (i < text.length()) {
            char c = text.charAt(i);
            if (c == '"' && field.isEmpty()) {
                int quoteLine = line;
                i++;
                while (true) {
                    if (i >= text.length()) {
                        throw CsvException.at(quoteLine, "unterminated quote");
                    }
                    char q = text.charAt(i);
                    if (q == '"') {
                        if (i + 1 < text.length() && text.charAt(i + 1) == '"') {
                            field.append('"');
                            i += 2;
                            continue;
                        }
                        i++;
                        break;
                    }
                    if (q == '\n') {
                        line++;
                    }
                    field.append(q);
                    i++;
                }
                if (i < text.length() && ",\r\n".indexOf(text.charAt(i)) < 0) {
                    throw CsvException.at(line, "unexpected character after quote");
                }
                rowStarted = true;
                continue;
            }
            if (c == ',') {
                row.add(field.toString());
                field.setLength(0);
                rowStarted = true;
                i++;
            } else if (c == '\r' || c == '\n') {
                row.add(field.toString());
                field.setLength(0);
                rows.add(row);
                lines.add(rowLine);
                row = new ArrayList<>();
                rowStarted = false;
                i += (c == '\r' && i + 1 < text.length() && text.charAt(i + 1) == '\n') ? 2 : 1;
                line++;
                rowLine = line;
            } else {
                field.append(c);
                rowStarted = true;
                i++;
            }
        }
        if (rowStarted) {
            row.add(field.toString());
            rows.add(row);
            lines.add(rowLine);
        }
        return new Parsed(rows, lines);
    }
}
