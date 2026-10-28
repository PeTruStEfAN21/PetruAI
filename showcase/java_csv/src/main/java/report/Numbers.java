package report;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class Numbers {

    private Numbers() {}

    public static BigDecimal parseDecimal(String s) {
        return new BigDecimal(s.trim());
    }

    public static String format(BigDecimal value) {
        // Round to 2 decimal places using HALF_UP
        BigDecimal rounded = value.setScale(2, RoundingMode.HALF_UP);
        // Strip trailing zeros but keep at least the integer part
        String s = rounded.stripTrailingZeros().toPlainString();
        return s;
    }

    public static int compareDecimal(String a, String b) {
        return new BigDecimal(a.trim()).compareTo(new BigDecimal(b.trim()));
    }
}
