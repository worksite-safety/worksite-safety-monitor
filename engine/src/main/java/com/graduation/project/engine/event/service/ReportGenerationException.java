package com.graduation.project.engine.event.service;

/**
 * The events PDF could not be produced.
 *
 * <h2>Why this type exists</h2>
 *
 * <p>{@code EventService.generateEventsPdf} used to catch {@code Exception}, call
 * {@code printStackTrace()} and return the {@code ByteArrayOutputStream} it had been writing into.
 * iText buffers the whole document until {@code Document.close()}, and the error path never
 * reached that call, so what came back was not a truncated PDF - it was ZERO bytes.
 * {@code EventController.sendPdfEmail} then attached those zero bytes to a mail, sent it, and
 * answered {@code 200 "Email sent successfully!"}. Both sides were silent: the operator got a mail
 * with an unopenable 0-byte {@code events_data.pdf} and a success toast, and the only trace of the
 * real failure was a stack trace on stdout.
 *
 * <p>A dedicated unchecked type rather than letting the original exception escape: the failures
 * that reach here are whatever iText or the event data throw - {@code NullPointerException},
 * {@code DocumentException}, an {@code IOException} - and the caller does not want to enumerate
 * them, it wants to know "the report was not produced" so it can say so instead of claiming
 * success. The cause is always attached, so nothing is lost.
 *
 * <p>Deliberately NOT one of the types in {@code core/exception}: those map to 4xx client errors
 * through {@code GenericExceptionHandler} ({@code EntityNotFoundException} to 404,
 * {@code BadRequestException} to 400), and a report that failed to render is a server-side
 * failure. {@code EventController} translates it to 500 at the one place it can occur.
 */
public class ReportGenerationException extends RuntimeException {

  public ReportGenerationException(String message, Throwable cause) {
    super(message, cause);
  }
}
