package exceptions;

/**
 * A runtime exception type for ASCII-art related failures.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * This exception handles runtime errors in the ASCII art algorithm
 */
public class AsciiArtException extends RuntimeException {

    /**
     * Constructs an {@link AsciiArtException} with no detail message.
     */
    public AsciiArtException() {
        super();
    }

    /**
     * Constructs an {@link AsciiArtException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public AsciiArtException(String message) {
        super(message);
    }

    /**
     * Constructs an {@link AsciiArtException} with the specified detail message and cause.
     *
     * @param message The detail message.
     * @param cause	The cause.
     */
    public AsciiArtException(String message, Throwable cause) {
        super(message, cause);
    }
}