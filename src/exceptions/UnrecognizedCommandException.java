package exceptions;

/**
 * Thrown when the user inputs a command that is not recognized by the Shell.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used for unrecognized commands instead of just printing error messages
 */
public class UnrecognizedCommandException extends ShellException {

	/**
	 * Constructs an UnrecognizedCommandException with the specified detail message.
	 *
	 * @param message The error detail message.
	 */
	public UnrecognizedCommandException(String message) {
		super(message);
	}

	/**
	 * Constructs an UnrecognizedCommandException with the specified detail message and cause.
	 *
	 * @param message The error detail message.
	 * @param cause The cause of the exception.
	 */
	public UnrecognizedCommandException(String message, Throwable cause) {
		super(message, cause);
	}
}