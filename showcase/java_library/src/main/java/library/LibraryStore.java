package library;

import java.io.BufferedWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class LibraryStore {

    private static final String TAB = "\t";

    public static void save(Library library, Path path) throws Exception {
        Path parent = path.getParent();
        if (parent != null && !Files.exists(parent)) {
            Files.createDirectories(parent);
        }

        try (BufferedWriter w = Files.newBufferedWriter(path)) {
            w.write("nextLoanNumber=" + library.getNextLoanNumber());
            w.newLine();

            // Books sorted by isbn (TreeMap is already sorted)
            for (Map.Entry<String, Book> entry : library.getBooks().entrySet()) {
                String isbn = entry.getKey();
                Book b = entry.getValue();
                w.write("book" + TAB + isbn + TAB + escape(b.title()) + TAB + escape(b.author()) + TAB + library.getCopies().get(isbn));
                w.newLine();
            }

            // Members sorted by id
            for (Map.Entry<String, Member> entry : library.getMembers().entrySet()) {
                String id = entry.getKey();
                Member m = entry.getValue();
                w.write("member" + TAB + id + TAB + escape(m.name()) + TAB + m.finesCents());
                w.newLine();
            }

            // Loans in insertion order
            for (Loan l : library.getLoans()) {
                w.write("loan" + TAB + l.id() + TAB + l.memberId() + TAB + l.isbn() + TAB + l.due() + TAB + l.returned());
                w.newLine();
            }
        }
    }

    public static Library load(Path path) throws Exception {
        List<String> lines = Files.readAllLines(path);
        Library lib = new Library();
        int nextLoanNumber = 1;

        for (String line : lines) {
            if (line.trim().isEmpty()) continue;

            if (line.startsWith("nextLoanNumber=")) {
                nextLoanNumber = Integer.parseInt(line.substring("nextLoanNumber=".length()));
                continue;
            }

            String[] parts = line.split(TAB, -1);
            String type = parts[0];

            if (type.equals("book")) {
                String isbn = parts[1];
                String title = unescape(parts[2]);
                String author = unescape(parts[3]);
                int copiesCount = Integer.parseInt(parts[4]);
                lib.addBook(isbn, title, author, copiesCount);
            } else if (type.equals("member")) {
                String id = parts[1];
                String name = unescape(parts[2]);
                int finesCents = Integer.parseInt(parts[3]);
                lib.addMember(id, name);
                lib.setMemberFines(id, finesCents);
            } else if (type.equals("loan")) {
                String loanId = parts[1];
                String memberId = parts[2];
                String isbn = parts[3];
                LocalDate due = LocalDate.parse(parts[4]);
                boolean returned = Boolean.parseBoolean(parts[5]);
                lib.addLoan(new Loan(loanId, memberId, isbn, due, returned));
            }
        }

        lib.setNextLoanNumber(nextLoanNumber);
        return lib;
    }

    private static String escape(String value) {
        if (value == null) return null;
        return value.replace("\\", "\\\\")
                   .replace("\t", "\\t")
                   .replace("\n", "\\n");
    }

    private static String unescape(String value) {
        if (value == null) return null;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '\\' && i + 1 < value.length()) {
                char next = value.charAt(i + 1);
                switch (next) {
                    case '\\': sb.append('\\'); i++; break;
                    case 't': sb.append('\t'); i++; break;
                    case 'n': sb.append('\n'); i++; break;
                    default: sb.append(c); break;
                }
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }
}
