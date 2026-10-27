package report;

public class CsvException extends RuntimeException {
    public CsvException(String message) {
        super(message);
    }

    static CsvException at(int line, String message) {
        return new CsvException("line " + line + ": " + message);
    }
}
