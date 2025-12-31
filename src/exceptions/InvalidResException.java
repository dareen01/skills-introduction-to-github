package exceptions;

/**
 * Thrown when the resolution command is invalid (wrong format or exceeds boundaries).
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used for res command errors instead of just printing error messages
 */
public class InvalidResException extends ShellException {

    /**
     * Constructs an {@link InvalidResException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public InvalidResException(String message) {
        super(message);
    }

    /**
     * Constructs an {@link InvalidResException} with the specified detail message and cause.
     *
     * @param message The detail message.
     * @param cause   The cause of the exception.
     */
    public InvalidResException(String message, Throwable cause) {
        super(message, cause);
    }
}