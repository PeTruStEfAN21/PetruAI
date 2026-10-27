package library;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

/** Loan rules: 14 days, 3 loans at once, 25 cents per late day capped at 10.00, blocked from 5.00 owed. */
public final class FinePolicy {
    public static final int LOAN_DAYS = 14;
    public static final int MAX_LOANS = 3;
    public static final int CENTS_PER_DAY = 25;
    public static final int MAX_FINE_CENTS = 1000;
    public static final int BLOCKING_FINES_CENTS = 500;

    private FinePolicy() {}

    public static LocalDate dueDate(LocalDate checkout) {
        return checkout.plusDays(LOAN_DAYS);
    }

    public static int fineFor(LocalDate due, LocalDate returned) {
        long late = ChronoUnit.DAYS.between(due, returned);
        if (late <= 0) {
            return 0;
        }
        return (int) Math.min(MAX_FINE_CENTS, late * CENTS_PER_DAY);
    }

    public static boolean blocked(Member member) {
        return member.finesCents() >= BLOCKING_FINES_CENTS;
    }
}
