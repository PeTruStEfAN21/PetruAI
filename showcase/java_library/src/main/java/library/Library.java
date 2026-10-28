package library;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class Library {
    private final Map<String, Book> books = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
    private final Map<String, Integer> copies = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
    private final Map<String, Member> members = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
    private final List<Loan> loans = new ArrayList<>();
    private int nextLoanNumber = 1;

    public void addBook(String isbn, String title, String author, int copiesCount) {
        if (books.containsKey(isbn)) {
            throw new IllegalArgumentException("duplicate isbn " + isbn);
        }
        if (copiesCount < 1) {
            throw new IllegalArgumentException("copies must be >= 1");
        }
        books.put(isbn, new Book(isbn, title, author));
        copies.put(isbn, copiesCount);
    }

    public void addCopies(String isbn, int n) {
        if (!books.containsKey(isbn)) {
            throw new LibraryException("unknown book " + isbn);
        }
        copies.put(isbn, copies.get(isbn) + n);
    }

    public void addMember(String id, String name) {
        if (members.containsKey(id)) {
            throw new IllegalArgumentException("duplicate member " + id);
        }
        members.put(id, new Member(id, name, 0));
    }

    public Book book(String isbn) {
        Book b = books.get(isbn);
        if (b == null) {
            throw new LibraryException("unknown book " + isbn);
        }
        return b;
    }

    public Member member(String id) {
        Member m = members.get(id);
        if (m == null) {
            throw new LibraryException("unknown member " + id);
        }
        return m;
    }

    public int available(String isbn) {
        Book b = books.get(isbn);
        if (b == null) return 0;
        int total = copies.get(isbn);
        int active = 0;
        for (Loan l : loans) {
            if (l.isbn().equals(isbn) && !l.returned()) active++;
        }
        return total - active;
    }

    public List<Book> search(String query) {
        List<Book> results = new ArrayList<>();
        String lower = query.toLowerCase();
        for (Book b : books.values()) {
            if (b.title().toLowerCase().contains(lower) || b.author().toLowerCase().contains(lower)) {
                results.add(b);
            }
        }
        results.sort(Comparator.comparing(Book::title));
        return results;
    }

    public Loan checkout(String memberId, String isbn, LocalDate day) {
        Member m = members.get(memberId);
        if (m == null) {
            throw new LibraryException("unknown member " + memberId);
        }
        Book b = books.get(isbn);
        if (b == null) {
            throw new LibraryException("unknown book " + isbn);
        }

        // Check unpaid fines (threshold check)
        if (m.finesCents() >= FinePolicy.FINE_THRESHOLD_CENTS) {
            throw new LibraryException("member " + memberId + " has unpaid fines");
        }

        // Check already has this book
        for (Loan l : loans) {
            if (l.memberId().equals(memberId) && !l.returned() && l.isbn().equals(isbn)) {
                throw new LibraryException("member " + memberId + " already has " + isbn);
            }
        }

        // Check active loans count
        long activeCount = 0;
        for (Loan l : loans) {
            if (l.memberId().equals(memberId) && !l.returned()) activeCount++;
        }
        if (activeCount >= FinePolicy.MAX_LOANS) {
            throw new LibraryException("member " + memberId + " has reached the loan limit");
        }

        // Check available copies
        int activeForBook = 0;
        for (Loan l : loans) {
            if (l.isbn().equals(isbn) && !l.returned()) activeForBook++;
        }
        int totalCopies = copies.get(isbn);
        if (activeForBook >= totalCopies) {
            throw new LibraryException("no copies of " + isbn + " available");
        }

        // Create loan
        String loanId = "L" + nextLoanNumber++;
        Loan loan = new Loan(loanId, memberId, isbn, day.plusDays(FinePolicy.LOAN_PERIOD_DAYS), false);
        loans.add(loan);
        return loan;
    }

    public int returnBook(String loanId, LocalDate day) {
        Loan loan = findLoan(loanId);
        if (loan == null) {
            throw new LibraryException("unknown loan " + loanId);
        }
        if (loan.returned()) {
            throw new LibraryException("loan " + loanId + " is already returned");
        }

        int fine = 0;
        if (day.isAfter(loan.due())) {
            long daysLate = java.time.temporal.ChronoUnit.DAYS.between(loan.due(), day);
            fine = (int) Math.min(daysLate * FinePolicy.FINE_PER_DAY_CENTS, FinePolicy.MAX_FINE_CENTS);
        }

        // Update member fines
        Member m = members.get(loan.memberId());
        members.put(loan.memberId(), new Member(m.id(), m.name(), m.finesCents() + fine));

        // Update loan
        for (int i = 0; i < loans.size(); i++) {
            if (loans.get(i).id().equals(loanId)) {
                loans.set(i, new Loan(loanId, loan.memberId(), loan.isbn(), loan.due(), true));
                break;
            }
        }

        return fine;
    }

    public void payFine(String memberId, int cents) {
        if (cents < 1) {
            throw new IllegalArgumentException("cents must be >= 1");
        }
        Member m = members.get(memberId);
        if (m == null) {
            throw new LibraryException("unknown member " + memberId);
        }
        if (cents > m.finesCents()) {
            throw new IllegalArgumentException("overpayment");
        }
        members.put(memberId, new Member(m.id(), m.name(), m.finesCents() - cents));
    }

    public List<Loan> activeLoans(String memberId) {
        List<Loan> result = new ArrayList<>();
        for (Loan l : loans) {
            if (l.memberId().equals(memberId) && !l.returned()) {
                result.add(l);
            }
        }
        result.sort(Comparator.comparing(Loan::due).thenComparing(Loan::id));
        return result;
    }

    public List<Loan> overdue(LocalDate day) {
        List<Loan> result = new ArrayList<>();
        for (Loan l : loans) {
            if (!l.returned() && l.due().isBefore(day)) {
                result.add(l);
            }
        }
        result.sort(Comparator.comparing(Loan::due).thenComparing(Loan::id));
        return result;
    }

    private Loan findLoan(String loanId) {
        for (Loan l : loans) {
            if (l.id().equals(loanId)) return l;
        }
        return null;
    }

    // Package-private methods for LibraryStore
    Map<String, Book> getBooks() { return books; }
    Map<String, Member> getMembers() { return members; }
    List<Loan> getLoans() { return loans; }
    Map<String, Integer> getCopies() { return copies; }
    int getNextLoanNumber() { return nextLoanNumber; }

    void setNextLoanNumber(int n) { nextLoanNumber = n; }
    void setMemberFines(String id, int fines) {
        Member m = members.get(id);
        if (m != null) {
            members.put(id, new Member(m.id(), m.name(), fines));
        }
    }
    void addLoan(Loan loan) { loans.add(loan); }
}
