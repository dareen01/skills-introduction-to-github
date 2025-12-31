package exceptions;

/**
 * Thrown when attempting to set an invalid resolution value.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used for resolution boundary violations
 */
public class InvalidResolutionException extends AsciiArtException {

    /**
     * Constructs an {@link InvalidResolutionException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public InvalidResolutionException(String message) {
        super(message);
    }
}