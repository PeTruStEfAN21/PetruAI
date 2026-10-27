package library;

/** A request the library refuses: unknown records or a rule that forbids it. */
public class LibraryException extends RuntimeException {
    public LibraryException(String message) {
        super(message);
    }
}
