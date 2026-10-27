package report;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;

class ReportTest {
    static final String SALES = String.join("\n",
        "city,product,price",
        "Iasi,apple,2.50",
        "Cluj,pear,3",
        "Iasi,\"melon, large\",10",
        "Bucuresti,apple,2.5",
        "Cluj,plum,1.25",
        "");

    @Test
    void parsesPlainAndQuotedFields() {
        assertThat(CsvParser.parse("a,b\n1,2\n")).containsExactly(List.of("a", "b"), List.of("1", "2"));
        assertThat(CsvParser.parse("a,b\r\n1,2")).containsExactly(List.of("a", "b"), List.of("1", "2"));
        assertThat(CsvParser.parse("\"x,y\",\"he said \"\"hi\"\"\"")).containsExactly(List.of("x,y", "he said \"hi\""));
        assertThat(CsvParser.parse("\"two\nlines\",z")).containsExactly(List.of("two\nlines", "z"));
        assertThat(CsvParser.parse(",,")).containsExactly(List.of("", "", ""));
        assertThat(CsvParser.parse("")).isEmpty();
    }

    @Test
    void reportsMalformedCsvWithLineNumbers() {
        assertThatThrownBy(() -> CsvParser.parse("a,b\n\"open,c\n"))
            .isInstanceOf(CsvException.class)
            .hasMessage("line 2: unterminated quote");
        assertThatThrownBy(() -> CsvParser.parse("\"a\"b,c"))
            .isInstanceOf(CsvException.class)
            .hasMessage("line 1: unexpected character after quote");
    }

    @Test
    void tableFromCsv() {
        Table t = Table.fromCsv(SALES);
        assertThat(t.columns()).containsExactly("city", "product", "price");
        assertThat(t.rowCount()).isEqualTo(5);
        assertThat(t.get(2, "product")).isEqualTo("melon, large");
        assertThat(t.column("city")).containsExactly("Iasi", "Cluj", "Iasi", "Bucuresti", "Cluj");
        assertThatThrownBy(() -> t.column("color"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("unknown column: color");
    }

    @Test
    void tableRejectsRaggedRowsAndEmptyInput() {
        assertThatThrownBy(() -> Table.fromCsv("a,b,c\n1,2,3\n4,5\n"))
            .isInstanceOf(CsvException.class)
            .hasMessage("line 3: expected 3 fields, got 2");
        assertThatThrownBy(() -> Table.fromCsv("")).isInstanceOf(CsvException.class).hasMessage("empty input");
    }

    @Test
    void whereAndSortReturnNewTables() {
        Table t = Table.fromCsv(SALES);
        Table iasi = t.where("city", v -> v.equals("Iasi"));
        assertThat(iasi.column("product")).containsExactly("apple", "melon, large");
        assertThat(t.rowCount()).isEqualTo(5);

        Table byPrice = t.sortBy("price", true, true);
        assertThat(byPrice.column("price")).containsExactly("10", "3", "2.50", "2.5", "1.25");
        Table byCity = t.sortBy("city", false, false);
        assertThat(byCity.column("product")).containsExactly("apple", "pear", "plum", "apple", "melon, large");
    }

    @Test
    void groupByWithAggregates() {
        Table t = Table.fromCsv(SALES);
        Table g = Aggregate.groupBy(t, "city",
            Aggregate.count(), Aggregate.sum("price"), Aggregate.avg("price"), Aggregate.max("price"));
        assertThat(g.columns()).containsExactly("city", "count", "sum_price", "avg_price", "max_price");
        assertThat(g.column("city")).containsExactly("Iasi", "Cluj", "Bucuresti");
        assertThat(g.column("count")).containsExactly("2", "2", "1");
        assertThat(g.column("sum_price")).containsExactly("12.5", "4.25", "2.5");
        assertThat(g.column("avg_price")).containsExactly("6.25", "2.13", "2.5");
        assertThat(g.column("max_price")).containsExactly("10", "3", "2.5");
    }

    @Test
    void aggregatesRejectNonNumbers() {
        Table t = Table.fromCsv("k,v\na,1\na,abc\n");
        assertThatThrownBy(() -> Aggregate.groupBy(t, "k", Aggregate.sum("v")))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("not a number in v: abc");
    }

    @Test
    void rendersAnAlignedTextTable() {
        Table g = Aggregate.groupBy(Table.fromCsv(SALES), "city", Aggregate.count(), Aggregate.sum("price"));
        assertThat(TextTable.render(g)).isEqualTo(String.join("\n",
            "city      | count | sum_price",
            "----------+-------+----------",
            "Iasi      |     2 |      12.5",
            "Cluj      |     2 |      4.25",
            "Bucuresti |     1 |       2.5"));
    }

    @Test
    void writesCsvWithQuotingWhereNeeded() {
        Table t = Table.fromCsv("name,note\nana,\"a, b\"\nbob,\"say \"\"hi\"\"\"\ncarl,\" padded\"\n");
        assertThat(CsvWriter.write(t)).isEqualTo(
            "name,note\nana,\"a, b\"\nbob,\"say \"\"hi\"\"\"\ncarl,\" padded\"\n");
        Table round = Table.fromCsv(CsvWriter.write(t));
        assertThat(round.column("note")).containsExactly("a, b", "say \"hi\"", " padded");
    }
}
