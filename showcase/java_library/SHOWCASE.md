# java_library

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build a library lending system in Java 21 (standard library only) in package `library` under src/main/java/library/. The acceptance tests are in src/test/java/library/LibraryTest.java (JUnit 5 + AssertJ); do not change them or pom.xml. `mvn -q test` must pass.

API (exact messages are in the tests):
- `record Book(isbn, title, author)`; `Member` with id(), name(), finesCents(); `Loan` with id() ("L1", "L2", ...), memberId(), isbn(), due(), returned(); `LibraryException extends RuntimeException`.
- `Library`: addBook(isbn, title, author, copies) (duplicate isbn or copies < 1 -> IllegalArgumentException), addCopies(isbn, n), addMember(id, name) (duplicate -> IllegalArgumentException), book(isbn) / member(id) (unknown -> LibraryException "unknown book 999" / "unknown member m9"), available(isbn), search(query) (title or author contains it, case-insensitive, sorted by title).
- checkout(memberId, isbn, LocalDate day) -> Loan due 14 days later. Refused with LibraryException when the member owes 500 cents or more ("member m1 has unpaid fines"), already has 3 active loans ("member m1 has reached the loan limit"), already has that book ("member m1 already has 111"), or no copy is free ("no copies of 111 available"), checked in that order.
- returnBook(loanId, day) -> the fine in cents: 25 per day after the due date, at most 1000, added to the member's fines; unknown or already returned loans are refused. payFine(memberId, cents) with 1 <= cents <= owed, else IllegalArgumentException.
- activeLoans(memberId) and overdue(day) (due before day), both sorted by due date then loan number.
- `LibraryStore.save(library, Path)` (creates folders) and `LibraryStore.load(Path)` round-trip everything, including titles with commas, quotes or semicolons, fines, returned loans and the next loan number.

Split the code into classes: Book, Member, Loan, LibraryException, FinePolicy (the loan and fine rules), Library, LibraryStore.

## Result

- Acceptance tests: passed
- Time: 28 min as a team, 15 min for the 35B alone
- Pieces handed to the assistant: 4

## Who wrote what

| File | Written by |
|---|---|
| `.gitignore` | not recorded |
| `.petru/DECISIONS.md` | not recorded |
| `pom.xml` | given with the task |
| `src/main/java/library/Book.java` | not recorded |
| `src/main/java/library/FinePolicy.java` | not recorded |
| `src/main/java/library/Library.java` | not recorded |
| `src/main/java/library/LibraryException.java` | not recorded |
| `src/main/java/library/LibraryStore.java` | not recorded |
| `src/main/java/library/Loan.java` | not recorded |
| `src/main/java/library/Member.java` | not recorded |
| `src/test/java/library/LibraryTest.java` | given with the task |

Who wrote the other files was not recorded: this run's conversation was summarised.
