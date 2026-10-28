package report;

public class CsvException extends RuntimeException {
    private final int lineNumber;

    public CsvException(int lineNumber, String message) {
        super("line " + lineNumber + ": " + message);
        this.lineNumber = lineNumber;
    }

    public int lineNumber() {
        return lineNumber;
    }
}
