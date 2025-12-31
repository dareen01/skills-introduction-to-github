package exceptions;

/**
 * Base checked exception type for shell/CLI command processing errors.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * This is the base exception class that all shell-related errors inherit from.
 * This allows us to use exceptions for ALL error cases as required in section 2.1.1
 */
public class ShellException extends Exception {

    /**
     * Constructs a {@link ShellException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public ShellException(String message) {
        super(message);
    }

    /**
     * Constructs a {@link ShellException} with the specified detail message and cause.
     *
     * @param message The detail message.
     * @param cause   The cause of the exception.
     */
    public ShellException(String message, Throwable cause) {
        super(message, cause);
    }
}