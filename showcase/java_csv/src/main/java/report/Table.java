package report;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Predicate;

public class Table {

    private final List<String> columns;
    private final List<List<String>> rows;

    Table(List<String> columns, List<List<String>> rows) {
        this.columns = columns;
        this.rows = rows;
    }

    public static Table fromCsv(String text) {
        List<List<String>> parsed = CsvParser.parse(text);
        if (parsed.isEmpty()) {
            throw new CsvException(0, "empty input");
        }

        List<String> header = parsed.get(0);
        List<List<String>> data = new ArrayList<>();
        int headerSize = header.size();

        for (int i = 1; i < parsed.size(); i++) {
            List<String> row = parsed.get(i);
            if (row.size() != headerSize) {
                throw new CsvException(i + 1, "expected " + headerSize + " fields, got " + row.size());
            }
            data.add(row);
        }

        return new Table(header, data);
    }

    public List<String> columns() {
        return columns;
    }

    public int rowCount() {
        return rows.size();
    }

    public List<String> row(int index) {
        return new ArrayList<>(rows.get(index));
    }

    public String get(int rowIndex, String columnName) {
        int colIndex = columns.indexOf(columnName);
        if (colIndex < 0) {
            throw new IllegalArgumentException("unknown column: " + columnName);
        }
        return rows.get(rowIndex).get(colIndex);
    }

    String get(int rowIndex, int colIndex) {
        return rows.get(rowIndex).get(colIndex);
    }

    public List<String> column(String name) {
        int colIndex = columns.indexOf(name);
        if (colIndex < 0) {
            throw new IllegalArgumentException("unknown column: " + name);
        }
        List<String> result = new ArrayList<>();
        for (List<String> row : rows) {
            result.add(row.get(colIndex));
        }
        return result;
    }

    public Table where(String column, Predicate<String> predicate) {
        List<List<String>> filteredRows = new ArrayList<>();
        for (List<String> row : rows) {
            String value = row.get(columns.indexOf(column));
            if (predicate.test(value)) {
                filteredRows.add(row);
            }
        }
        return new Table(columns, filteredRows);
    }

    public Table sortBy(String column, boolean numeric, boolean descending) {
        List<List<String>> sortedRows = new ArrayList<>(rows);
        List<String> cols = columns;
        int colIndex = cols.indexOf(column);

        Comparator<List<String>> comparator = (r1, r2) -> {
            String v1 = r1.get(colIndex);
            String v2 = r2.get(colIndex);

            int cmp;
            if (numeric) {
                cmp = Numbers.compareDecimal(v1, v2);
            } else {
                cmp = v1.compareTo(v2);
            }

            if (cmp != 0) {
                return descending ? -cmp : cmp;
            }
            return 0;
        };

        sortedRows.sort(comparator);
        return new Table(cols, sortedRows);
    }
}
