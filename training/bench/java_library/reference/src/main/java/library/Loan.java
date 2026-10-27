package library;

import java.time.LocalDate;

public final class Loan {
    private final String id;
    private final String memberId;
    private final String isbn;
    private final LocalDate due;
    private LocalDate returned;

    public Loan(String id, String memberId, String isbn, LocalDate due, LocalDate returned) {
        this.id = id;
        this.memberId = memberId;
        this.isbn = isbn;
        this.due = due;
        this.returned = returned;
    }

    public String id() {
        return id;
    }

    public String memberId() {
        return memberId;
    }

    public String isbn() {
        return isbn;
    }

    public LocalDate due() {
        return due;
    }

    public LocalDate returned() {
        return returned;
    }

    public boolean isActive() {
        return returned == null;
    }

    void markReturned(LocalDate day) {
        returned = day;
    }

    int number() {
        return Integer.parseInt(id.substring(1));
    }
}
