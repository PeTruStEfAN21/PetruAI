package library;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

/**
 * A plain text file, one record per line: "book", "member" or "loan" followed by tab-separated fields.
 * Backslash, tab and newline inside a field are escaped.
 */
public final class LibraryStore {
    private LibraryStore() {}

    public static void save(Library lib, Path file) throws IOException {
        List<String> lines = new ArrayList<>();
        for (Book b : lib.books()) {
            lines.add(join("book", b.isbn(), b.title(), b.author(), String.valueOf(lib.copies(b.isbn()))));
        }
        for (Member m : lib.members()) {
            lines.add(join("member", m.id(), m.name(), String.valueOf(m.finesCents())));
        }
        for (Loan l : lib.loans()) {
            String returned = l.returned() == null ? "" : l.returned().toString();
            lines.add(join("loan", l.id(), l.memberId(), l.isbn(), l.due().toString(), returned));
        }
        if (file.getParent() != null) {
            Files.createDirectories(file.getParent());
        }
        Files.write(file, lines, StandardCharsets.UTF_8);
    }

    public static Library load(Path file) throws IOException {
        Library lib = new Library();
        int lineNo = 0;
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            lineNo++;
            if (line.isEmpty()) {
                continue;
            }
            List<String> f = split(line);
            switch (f.get(0)) {
                case "book" -> lib.addBook(f.get(1), f.get(2), f.get(3), Integer.parseInt(f.get(4)));
                case "member" -> lib.restoreMember(new Member(f.get(1), f.get(2), Integer.parseInt(f.get(3))));
                case "loan" -> lib.restoreLoan(new Loan(
                    f.get(1), f.get(2), f.get(3), LocalDate.parse(f.get(4)),
                    f.get(5).isEmpty() ? null : LocalDate.parse(f.get(5))));
                default -> throw new IOException("line " + lineNo + ": unknown record " + f.get(0));
            }
        }
        return lib;
    }

    private static String join(String... fields) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < fields.length; i++) {
            if (i > 0) {
                sb.append('\t');
            }
            sb.append(fields[i].replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n"));
        }
        return sb.toString();
    }

    private static List<String> split(String line) {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (c == '\\' && i + 1 < line.length()) {
                char next = line.charAt(++i);
                current.append(next == 't' ? '\t' : next == 'n' ? '\n' : next);
            } else if (c == '\t') {
                fields.add(current.toString());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        fields.add(current.toString());
        return fields;
    }
}
