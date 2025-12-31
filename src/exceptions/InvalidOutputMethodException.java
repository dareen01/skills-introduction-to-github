package exceptions;

/**
 * Thrown when the output command has an invalid format or unsupported output method.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used for output command errors instead of just printing error messages
 */
public class InvalidOutputMethodException extends ShellException {

    /**
     * Constructs an {@link InvalidOutputMethodException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public InvalidOutputMethodException(String message) {
        super(message);
    }

    /**
     * Constructs an {@link InvalidOutputMethodException} with the specified detail message and cause.
     *
     * @param message The detail message.
     * @param cause   The cause of the exception.
     */
    public InvalidOutputMethodException(String message, Throwable cause) {
        super(message, cause);
    }
}