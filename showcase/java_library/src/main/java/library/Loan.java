package library;

import java.time.LocalDate;

public record Loan(String id, String memberId, String isbn, LocalDate due, boolean returned) {
}
