package exceptions;

/**
 * Thrown when a command has an invalid format.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used for add/remove commands with incorrect format instead of just printing error messages
 */
public class InvalidFormatException extends ShellException {

    /**
     * Constructs an {@link InvalidFormatException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public InvalidFormatException(String message) {
        super(message);
    }

    /**
     * Constructs an {@link InvalidFormatException} with the specified detail message and cause.
     *
     * @param message The detail message.
     * @param cause   The cause of the exception.
     */
    public InvalidFormatException(String message, Throwable cause) {
        super(message, cause);
    }
}