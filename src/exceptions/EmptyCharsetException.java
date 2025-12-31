package exceptions;

/**
 * Thrown when an operation requires a non-empty charset but the charset is empty.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used when charset is too small for ASCII art generation
 */
public class EmptyCharsetException extends AsciiArtException {

    /**
     * Constructs an {@link EmptyCharsetException} with no detail message.
     */
    public EmptyCharsetException() {
        super();
    }

    /**
     * Constructs an {@link EmptyCharsetException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public EmptyCharsetException(String message) {
        super(message);
    }
}