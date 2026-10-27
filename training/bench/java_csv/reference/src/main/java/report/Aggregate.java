package report;

import java.math.BigDecimal;
import java.math.MathContext;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Group-by with aggregate columns; groups keep the order in which they first appear. */
public final class Aggregate {
    /** One output column computed from the rows of a group. */
    public interface Aggregator {
        String name();

        String apply(Table table, List<Integer> rows);
    }

    private Aggregate() {}

    public static Aggregator count() {
        return simple("count", (table, rows) -> String.valueOf(rows.size()));
    }

    public static Aggregator sum(String column) {
        return simple("sum_" + column, (table, rows) -> Numbers.format(total(table, column, rows)));
    }

    public static Aggregator avg(String column) {
        return simple("avg_" + column, (table, rows) -> Numbers.format(
            total(table, column, rows).divide(BigDecimal.valueOf(rows.size()), MathContext.DECIMAL64)));
    }

    public static Aggregator max(String column) {
        return simple("max_" + column, (table, rows) -> Numbers.format(rows.stream()
            .map(r -> Numbers.parse(column, table.get(r, column)))
            .reduce(BigDecimal::max)
            .orElse(BigDecimal.ZERO)));
    }

    public static Table groupBy(Table table, String key, Aggregator... aggregators) {
        Map<String, List<Integer>> groups = new LinkedHashMap<>();
        List<String> keys = table.column(key);
        for (int i = 0; i < keys.size(); i++) {
            groups.computeIfAbsent(keys.get(i), k -> new ArrayList<>()).add(i);
        }
        List<String> columns = new ArrayList<>(List.of(key));
        for (Aggregator a : aggregators) {
            columns.add(a.name());
        }
        List<List<String>> rows = new ArrayList<>();
        for (Map.Entry<String, List<Integer>> group : groups.entrySet()) {
            List<String> row = new ArrayList<>(List.of(group.getKey()));
            for (Aggregator a : aggregators) {
                row.add(a.apply(table, group.getValue()));
            }
            rows.add(row);
        }
        return new Table(columns, rows);
    }

    private static BigDecimal total(Table table, String column, List<Integer> rows) {
        BigDecimal sum = BigDecimal.ZERO;
        for (int r : rows) {
            sum = sum.add(Numbers.parse(column, table.get(r, column)));
        }
        return sum;
    }

    private interface Body {
        String apply(Table table, List<Integer> rows);
    }

    private static Aggregator simple(String name, Body body) {
        return new Aggregator() {
            @Override
            public String name() {
                return name;
            }

            @Override
            public String apply(Table table, List<Integer> rows) {
                return body.apply(table, rows);
            }
        };
    }
}
