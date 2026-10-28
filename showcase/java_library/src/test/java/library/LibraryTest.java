package library;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import java.time.LocalDate;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LibraryTest {
    static final LocalDate DAY = LocalDate.of(2026, 11, 2);
    Library lib;

    @BeforeEach
    void setUp() {
        lib = new Library();
        lib.addBook("111", "Dune", "Frank Herbert", 2);
        lib.addBook("222", "Emma", "Jane Austen", 1);
        lib.addBook("333", "Persuasion", "Jane Austen", 1);
        lib.addMember("m1", "Ana");
        lib.addMember("m2", "Bogdan");
    }

    @Test
    void booksAndMembers() {
        assertThat(lib.book("111").title()).isEqualTo("Dune");
        assertThat(lib.member("m2").name()).isEqualTo("Bogdan");
        assertThat(lib.available("111")).isEqualTo(2);
        assertThatThrownBy(() -> lib.addBook("111", "Again", "X", 1)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> lib.addMember("m1", "Again")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> lib.addBook("444", "Zero", "X", 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> lib.book("999")).isInstanceOf(LibraryException.class).hasMessage("unknown book 999");
        assertThatThrownBy(() -> lib.member("m9")).isInstanceOf(LibraryException.class).hasMessage("unknown member m9");
    }

    @Test
    void addingCopiesOfAKnownBook() {
        lib.addCopies("222", 2);
        assertThat(lib.available("222")).isEqualTo(3);
    }

    @Test
    void searchIsCaseInsensitiveAndSortedByTitle() {
        assertThat(lib.search("austen")).extracting(Book::title).containsExactly("Emma", "Persuasion");
        assertThat(lib.search("DUN")).extracting(Book::isbn).containsExactly("111");
        assertThat(lib.search("nothing")).isEmpty();
    }

    @Test
    void checkoutCreatesLoansDueInFourteenDays() {
        Loan loan = lib.checkout("m1", "111", DAY);
        assertThat(loan.id()).isEqualTo("L1");
        assertThat(loan.memberId()).isEqualTo("m1");
        assertThat(loan.isbn()).isEqualTo("111");
        assertThat(loan.due()).isEqualTo(DAY.plusDays(14));
        assertThat(lib.available("111")).isEqualTo(1);
        assertThat(lib.checkout("m2", "111", DAY).id()).isEqualTo("L2");
        lib.addMember("m3", "Carmen");
        assertThatThrownBy(() -> lib.checkout("m3", "111", DAY))
            .isInstanceOf(LibraryException.class)
            .hasMessage("no copies of 111 available");
    }

    @Test
    void loanLimitIsThree() {
        lib.addBook("444", "Ulysses", "James Joyce", 1);
        lib.checkout("m1", "111", DAY);
        lib.checkout("m1", "222", DAY);
        lib.checkout("m1", "333", DAY);
        assertThatThrownBy(() -> lib.checkout("m1", "444", DAY))
            .isInstanceOf(LibraryException.class)
            .hasMessage("member m1 has reached the loan limit");
    }

    @Test
    void sameBookTwiceIsRefused() {
        lib.checkout("m1", "111", DAY);
        assertThatThrownBy(() -> lib.checkout("m1", "111", DAY))
            .isInstanceOf(LibraryException.class)
            .hasMessage("member m1 already has 111");
    }

    @Test
    void returningOnTimeCostsNothing() {
        Loan loan = lib.checkout("m1", "222", DAY);
        assertThat(lib.returnBook(loan.id(), DAY.plusDays(14))).isZero();
        assertThat(lib.available("222")).isEqualTo(1);
        assertThat(lib.activeLoans("m1")).isEmpty();
        assertThatThrownBy(() -> lib.returnBook(loan.id(), DAY))
            .isInstanceOf(LibraryException.class)
            .hasMessage("loan L1 is already returned");
        assertThatThrownBy(() -> lib.returnBook("L77", DAY)).hasMessage("unknown loan L77");
    }

    @Test
    void lateReturnsAreFinedAndCapped() {
        Loan late = lib.checkout("m1", "222", DAY);
        assertThat(lib.returnBook(late.id(), DAY.plusDays(17))).isEqualTo(75);
        Loan veryLate = lib.checkout("m2", "333", DAY);
        assertThat(lib.returnBook(veryLate.id(), DAY.plusDays(200))).isEqualTo(1000);
        assertThat(lib.member("m1").finesCents()).isEqualTo(75);
        assertThat(lib.member("m2").finesCents()).isEqualTo(1000);
    }

    @Test
    void unpaidFinesBlockCheckoutUntilPaid() {
        Loan loan = lib.checkout("m1", "222", DAY);
        lib.returnBook(loan.id(), DAY.plusDays(34)); // 20 days late: 500
        assertThatThrownBy(() -> lib.checkout("m1", "111", DAY))
            .isInstanceOf(LibraryException.class)
            .hasMessage("member m1 has unpaid fines");
        lib.payFine("m1", 100);
        assertThat(lib.member("m1").finesCents()).isEqualTo(400);
        assertThat(lib.checkout("m1", "111", DAY).id()).isEqualTo("L2");
        assertThatThrownBy(() -> lib.payFine("m1", 401)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> lib.payFine("m1", 0)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void activeAndOverdueLoans() {
        lib.checkout("m1", "111", DAY.plusDays(2));
        lib.checkout("m1", "222", DAY);
        lib.checkout("m2", "333", DAY.plusDays(1));
        assertThat(lib.activeLoans("m1")).extracting(Loan::isbn).containsExactly("222", "111");
        assertThat(lib.overdue(DAY.plusDays(16))).extracting(Loan::id).containsExactly("L2", "L3");
        assertThat(lib.overdue(DAY.plusDays(14))).isEmpty();
    }

    @Test
    void stateRoundTripsThroughAFile(@TempDir Path dir) throws Exception {
        lib.addBook("555", "Title, with \"quotes\"", "Some; Author", 1);
        Loan open = lib.checkout("m1", "555", DAY);
        Loan done = lib.checkout("m2", "222", DAY);
        lib.returnBook(done.id(), DAY.plusDays(15));
        Path file = dir.resolve("sub").resolve("library.txt");
        LibraryStore.save(lib, file);

        Library again = LibraryStore.load(file);
        assertThat(again.book("555").title()).isEqualTo("Title, with \"quotes\"");
        assertThat(again.book("555").author()).isEqualTo("Some; Author");
        assertThat(again.available("555")).isZero();
        assertThat(again.available("222")).isEqualTo(1);
        assertThat(again.member("m2").finesCents()).isEqualTo(25);
        assertThat(again.activeLoans("m1")).extracting(Loan::id).containsExactly(open.id());
        assertThat(again.checkout("m2", "111", DAY).id()).isEqualTo("L3");
    }
}
