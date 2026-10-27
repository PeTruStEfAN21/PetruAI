package library;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class Library {
    private final Map<String, Book> books = new LinkedHashMap<>();
    private final Map<String, Integer> copies = new LinkedHashMap<>();
    private final Map<String, Member> members = new LinkedHashMap<>();
    private final Map<String, Loan> loans = new LinkedHashMap<>();
    private int nextLoan = 1;

    public Book addBook(String isbn, String title, String author, int count) {
        if (books.containsKey(isbn)) {
            throw new IllegalArgumentException("book " + isbn + " already exists");
        }
        if (count < 1) {
            throw new IllegalArgumentException("a book needs at least one copy");
        }
        Book book = new Book(isbn, title, author);
        books.put(isbn, book);
        copies.put(isbn, count);
        return book;
    }

    public void addCopies(String isbn, int count) {
        book(isbn);
        if (count < 1) {
            throw new IllegalArgumentException("count must be positive");
        }
        copies.merge(isbn, count, Integer::sum);
    }

    public Member addMember(String id, String name) {
        if (members.containsKey(id)) {
            throw new IllegalArgumentException("member " + id + " already exists");
        }
        Member member = new Member(id, name, 0);
        members.put(id, member);
        return member;
    }

    public Book book(String isbn) {
        Book book = books.get(isbn);
        if (book == null) {
            throw new LibraryException("unknown book " + isbn);
        }
        return book;
    }

    public Member member(String id) {
        Member member = members.get(id);
        if (member == null) {
            throw new LibraryException("unknown member " + id);
        }
        return member;
    }

    public int copies(String isbn) {
        book(isbn);
        return copies.get(isbn);
    }

    public int available(String isbn) {
        long lent = loans.values().stream().filter(l -> l.isActive() && l.isbn().equals(isbn)).count();
        return copies(isbn) - (int) lent;
    }

    public List<Book> search(String query) {
        String q = query.toLowerCase(Locale.ROOT);
        return books.values().stream()
            .filter(b -> b.title().toLowerCase(Locale.ROOT).contains(q) || b.author().toLowerCase(Locale.ROOT).contains(q))
            .sorted(Comparator.comparing(Book::title))
            .toList();
    }

    public Loan checkout(String memberId, String isbn, LocalDate day) {
        Member member = member(memberId);
        book(isbn);
        List<Loan> active = activeLoans(memberId);
        if (FinePolicy.blocked(member)) {
            throw new LibraryException("member " + memberId + " has unpaid fines");
        }
        if (active.size() >= FinePolicy.MAX_LOANS) {
            throw new LibraryException("member " + memberId + " has reached the loan limit");
        }
        if (active.stream().anyMatch(l -> l.isbn().equals(isbn))) {
            throw new LibraryException("member " + memberId + " already has " + isbn);
        }
        if (available(isbn) < 1) {
            throw new LibraryException("no copies of " + isbn + " available");
        }
        Loan loan = new Loan("L" + nextLoan++, memberId, isbn, FinePolicy.dueDate(day), null);
        loans.put(loan.id(), loan);
        return loan;
    }

    /** Returns the fine charged for this loan, in cents. */
    public int returnBook(String loanId, LocalDate day) {
        Loan loan = loans.get(loanId);
        if (loan == null) {
            throw new LibraryException("unknown loan " + loanId);
        }
        if (!loan.isActive()) {
            throw new LibraryException("loan " + loanId + " is already returned");
        }
        loan.markReturned(day);
        int fine = FinePolicy.fineFor(loan.due(), day);
        member(loan.memberId()).addFine(fine);
        return fine;
    }

    public void payFine(String memberId, int cents) {
        member(memberId).pay(cents);
    }

    public List<Loan> activeLoans(String memberId) {
        member(memberId);
        return loans.values().stream()
            .filter(l -> l.isActive() && l.memberId().equals(memberId))
            .sorted(Comparator.comparing(Loan::due).thenComparing(Loan::number))
            .toList();
    }

    public List<Loan> overdue(LocalDate day) {
        return loans.values().stream()
            .filter(l -> l.isActive() && l.due().isBefore(day))
            .sorted(Comparator.comparing(Loan::due).thenComparing(Loan::number))
            .toList();
    }

    // used by LibraryStore

    Collection<Book> books() {
        return books.values();
    }

    Collection<Member> members() {
        return members.values();
    }

    Collection<Loan> loans() {
        return new ArrayList<>(loans.values());
    }

    void restoreMember(Member member) {
        members.put(member.id(), member);
    }

    void restoreLoan(Loan loan) {
        loans.put(loan.id(), loan);
        nextLoan = Math.max(nextLoan, loan.number() + 1);
    }
}
