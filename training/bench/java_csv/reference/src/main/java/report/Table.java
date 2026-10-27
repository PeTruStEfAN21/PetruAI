package report;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Predicate;

/** An immutable table of strings with named columns. */
public final class Table {
    private final List<String> columns;
    private final List<List<String>> rows;

    public Table(List<String> columns, List<List<String>> rows) {
        this.columns = List.copyOf(columns);
        this.rows = rows.stream().map(List::copyOf).toList();
    }

    public static Table fromCsv(String text) {
        CsvParser.Parsed parsed = CsvParser.parseWithLines(text);
        if (parsed.rows().isEmpty()) {
            throw new CsvException("empty input");
        }
        List<String> header = parsed.rows().get(0);
        List<List<String>> body = parsed.rows().subList(1, parsed.rows().size());
        for (int i = 0; i < body.size(); i++) {
            if (body.get(i).size() != header.size()) {
                throw CsvException.at(parsed.lines().get(i + 1),
                    "expected " + header.size() + " fields, got " + body.get(i).size());
            }
        }
        return new Table(header, body);
    }

    public List<String> columns() {
        return columns;
    }

    public int rowCount() {
        return rows.size();
    }

    public List<String> row(int index) {
        return rows.get(index);
    }

    public String get(int row, String column) {
        return rows.get(row).get(indexOf(column));
    }

    public List<String> column(String name) {
        int index = indexOf(name);
        return rows.stream().map(r -> r.get(index)).toList();
    }

    public Table where(String column, Predicate<String> test) {
        int index = indexOf(column);
        return new Table(columns, rows.stream().filter(r -> test.test(r.get(index))).toList());
    }

    /** A stable sort on one column, as text or as numbers. */
    public Table sortBy(String column, boolean numeric, boolean descending) {
        int index = indexOf(column);
        Comparator<List<String>> order = numeric
            ? Comparator.comparing(r -> Numbers.parse(column, r.get(index)), BigDecimal::compareTo)
            : Comparator.comparing(r -> r.get(index));
        if (descending) {
            order = order.reversed();
        }
        List<List<String>> sorted = new ArrayList<>(rows);
        sorted.sort(order);
        return new Table(columns, sorted);
    }

    int indexOf(String column) {
        int index = columns.indexOf(column);
        if (index < 0) {
            throw new IllegalArgumentException("unknown column: " + column);
        }
        return index;
    }
}
