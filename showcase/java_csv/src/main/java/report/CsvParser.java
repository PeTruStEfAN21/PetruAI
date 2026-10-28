package report;

import java.util.ArrayList;
import java.util.List;

public class CsvParser {

    public static List<List<String>> parse(String input) {
        if (input.isEmpty()) {
            return new ArrayList<>();
        }

        List<List<String>> rows = new ArrayList<>();
        int pos = 0;
        int len = input.length();

        while (pos < len) {
            // Skip trailing newline at end of input
            if (pos == len - 1 && input.charAt(pos) == '\n') {
                break;
            }
            if (pos + 1 < len && input.charAt(pos) == '\r' && input.charAt(pos + 1) == '\n') {
                break;
            }

            List<String> row = new ArrayList<>();
            int line = 1;
            for (int k = 0; k < pos; k++) {
                if (input.charAt(k) == '\n') line++;
            }

            // Parse first field
            String[] result = parseField(input, pos, len, line);
            row.add(result[0]);
            pos = Integer.parseInt(result[1]);

            while (pos < len) {
                char c = input.charAt(pos);
                if (c == ',') {
                    // Check for trailing comma at end of line
                    int afterComma = pos + 1;
                    if (afterComma < len && input.charAt(afterComma) == '\n') {
                        row.add("");
                        pos = afterComma + 1;
                        break;
                    }
                    if (afterComma + 1 < len && input.charAt(afterComma) == '\r' && input.charAt(afterComma + 1) == '\n') {
                        row.add("");
                        pos = afterComma + 2;
                        break;
                    }
                    if (afterComma >= len) {
                        row.add("");
                        pos = afterComma;
                        break;
                    }
                    // Parse next field
                    int fieldLine = 1;
                    for (int k = 0; k < afterComma; k++) {
                        if (input.charAt(k) == '\n') fieldLine++;
                    }
                    String[] next = parseField(input, afterComma, len, fieldLine);
                    row.add(next[0]);
                    pos = Integer.parseInt(next[1]);
                } else if (c == '\r') {
                    if (pos + 1 < len && input.charAt(pos + 1) == '\n') {
                        pos = pos + 2;
                    } else {
                        pos = pos + 1;
                    }
                    break;
                } else if (c == '\n') {
                    pos = pos + 1;
                    break;
                } else {
                    // Invalid character after field — not a delimiter or newline
                    throw new CsvException(line, "unexpected character after field");
                }
            }

            rows.add(row);
        }

        return rows;
    }

    /**
     * Parse a field starting at pos.
     * Returns [fieldValue, nextPosition] where nextPosition is the index in input
     * right after the field (i.e. at the comma, newline, or end).
     */
    private static String[] parseField(String input, int pos, int len, int startLine) {
        if (pos >= len) {
            return new String[]{"", String.valueOf(pos)};
        }

        if (input.charAt(pos) == '"') {
            // Quoted field
            StringBuilder sb = new StringBuilder();
            int i = pos + 1;
            while (i < len) {
                char c = input.charAt(i);
                if (c == '"') {
                    if (i + 1 < len && input.charAt(i + 1) == '"') {
                        sb.append('"');
                        i += 2;
                    } else {
                        // Closing quote at i, next char is at i+1
                        return new String[]{sb.toString(), String.valueOf(i + 1)};
                    }
                } else if (c == '\n') {
                    sb.append('\n');
                    i++;
                } else if (c == '\r') {
                    if (i + 1 < len && input.charAt(i + 1) == '\n') {
                        sb.append('\n');
                        i += 2;
                    } else {
                        sb.append('\r');
                        i++;
                    }
                } else {
                    sb.append(c);
                    i++;
                }
            }
            throw new CsvException(startLine, "unterminated quote");
        } else {
            // Unquoted field
            int end = pos;
            while (end < len && input.charAt(end) != ',' && input.charAt(end) != '\n' && input.charAt(end) != '\r') {
                end++;
            }
            return new String[]{input.substring(pos, end), String.valueOf(end)};
        }
    }
}
