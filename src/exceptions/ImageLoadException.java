package exceptions;

/**
 * Thrown when there is an error loading an image.
 * 
 * ADDED TO FIX: MANUAL.README.missing_exception_creation
 * Used for image loading errors (this was already partially implemented)
 */
public class ImageLoadException extends ShellException {

    /**
     * Constructs an {@link ImageLoadException} with the specified detail message.
     *
     * @param message The detail message.
     */
    public ImageLoadException(String message) {
        super(message);
    }

    /**
     * Constructs an {@link ImageLoadException} with the specified detail message and cause.
     *
     * @param message The detail message.
     * @param cause   The cause of the exception.
     */
    public ImageLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}