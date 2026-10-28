package report;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Aggregate {

    public static Aggregator count() {
        return new Aggregator("count", null);
    }

    public static Aggregator sum(String column) {
        return new Aggregator("sum_" + column, column);
    }

    public static Aggregator avg(String column) {
        return new Aggregator("avg_" + column, column);
    }

    public static Aggregator max(String column) {
        return new Aggregator("max_" + column, column);
    }

    public static Table groupBy(Table table, String keyColumn, Aggregator... aggregators) {
        int keyIdx = table.columns().indexOf(keyColumn);
        if (keyIdx == -1) {
            throw new IllegalArgumentException("unknown column: " + keyColumn);
        }

        // Preserve order of first appearance
        List<String> keys = new ArrayList<>();
        Map<String, List<Integer>> keyToIndices = new LinkedHashMap<>();

        for (int i = 0; i < table.rowCount(); i++) {
            String key = table.get(i, keyIdx);
            keyToIndices.computeIfAbsent(key, k -> new ArrayList<>()).add(i);
            if (!keys.contains(key)) {
                keys.add(key);
            }
        }

        // Build result columns
        List<String> resultColumns = new ArrayList<>();
        resultColumns.add(keyColumn);
        for (Aggregator agg : aggregators) {
            resultColumns.add(agg.name);
        }

        // Build result rows
        List<List<String>> resultRows = new ArrayList<>();
        for (String key : keys) {
            List<String> row = new ArrayList<>();
            row.add(key);
            for (Aggregator agg : aggregators) {
                row.add(agg.compute(table, key, keyIdx));
            }
            resultRows.add(row);
        }

        return new Table(resultColumns, resultRows);
    }

    public static final class Aggregator {
        final String name;
        final String column;

        Aggregator(String name, String column) {
            this.name = name;
            this.column = column;
        }

        String compute(Table table, String key, int keyIdx) {
            if (column == null) {
                // count
                int count = 0;
                for (int i = 0; i < table.rowCount(); i++) {
                    if (table.get(i, keyIdx).equals(key)) count++;
                }
                return String.valueOf(count);
            }

            List<BigDecimal> values = new ArrayList<>();
            for (int i = 0; i < table.rowCount(); i++) {
                if (table.get(i, keyIdx).equals(key)) {
                    try {
                        values.add(Numbers.parseDecimal(table.get(i, column)));
                    } catch (NumberFormatException e) {
                        throw new IllegalArgumentException("not a number in " + column + ": " + table.get(i, column));
                    }
                }
            }

            if (name.startsWith("sum_")) {
                BigDecimal sum = BigDecimal.ZERO;
                for (BigDecimal v : values) sum = sum.add(v);
                return Numbers.format(sum);
            } else if (name.startsWith("avg_")) {
                BigDecimal sum = BigDecimal.ZERO;
                for (BigDecimal v : values) sum = sum.add(v);
                return Numbers.format(sum.divide(BigDecimal.valueOf(values.size()), 10, RoundingMode.HALF_UP));
            } else if (name.startsWith("max_")) {
                BigDecimal max = values.get(0);
                for (int i = 1; i < values.size(); i++) {
                    if (values.get(i).compareTo(max) > 0) max = values.get(i);
                }
                return Numbers.format(max);
            }
            return "";
        }
    }
}
