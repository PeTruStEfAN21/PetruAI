package report;

import java.math.BigDecimal;
import java.math.RoundingMode;

/** Decimal parsing and the report's number format: at most two decimals, no trailing zeros. */
final class Numbers {
    private Numbers() {}

    static boolean isNumber(String text) {
        try {
            new BigDecimal(text.trim());
            return true;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    static BigDecimal parse(String column, String text) {
        try {
            return new BigDecimal(text.trim());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("not a number in " + column + ": " + text);
        }
    }

    static String format(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString();
    }
}
