package com.graduation.project.engine.event.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.service.EventService;
import com.graduation.project.engine.event.service.ReportGenerationException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.ResponseEntity;

/**
 * What {@code POST /event/sendPdfEmail/...} tells its caller.
 *
 * <p>Plain Mockito rather than {@code @WebMvcTest}: the only thing under test is the branch the
 * controller takes and the body it returns, and a MockMvc slice would drag in the whole security
 * filter chain - already characterized by {@code SecurityMatrixTest} - to prove nothing extra.
 *
 * <p>The reason this class exists at all is the half of the zero-byte-PDF defect that lives on
 * the controller side. {@code EventService.generateEventsPdf} swallowed its exception and returned
 * an empty stream; the controller could not tell, so it mailed 0 bytes and answered
 * {@code 200 "Email sent successfully!"}. Fixing only the service would have been enough to make
 * the exception exist, and not enough to make the CALLER see it - the controller has to stop
 * claiming success, and that claim is what these tests pin.
 */
@ExtendWith(MockitoExtension.class)
class EventControllerTest {

  private static final Long START = 1_600_000_000_000L;
  private static final Long END = 1_800_000_000_000L;
  private static final String RECIPIENT = "operator@example.com";

  @Mock
  private EventService eventService;

  @Mock
  private MailService mailService;

  @InjectMocks
  private EventController eventController;

  @Captor
  private ArgumentCaptor<byte[]> pdfCaptor;

  // -------------------------------------------------------------------------------------------
  // Happy path
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("sendPdfEmail: a generated report is mailed and answered with 200")
  void sendPdfEmail_happyPath_mailsThePdfAndReturns200() {
    List<Event> events = List.of(
        Event.builder().eventType(EventNameEnum.FALL.name()).startTime(START).build());
    when(eventService.getAllEventsByDateIntervals(START, END)).thenReturn(events);
    when(eventService.generateEventsPdf(events, START, END)).thenReturn(pdfBytes("%PDF-1.4 real"));

    ResponseEntity<String> response = eventController.sendPdfEmail(START, END, RECIPIENT);

    assertThat(response.getStatusCode().value()).isEqualTo(200);
    assertThat(response.getBody()).isEqualTo("Email sent successfully!");

    verify(mailService).sendEventsPdfEmail(eq(RECIPIENT), pdfCaptor.capture());
    assertThat(new String(pdfCaptor.getValue(), StandardCharsets.ISO_8859_1))
        .isEqualTo("%PDF-1.4 real");
  }

  // -------------------------------------------------------------------------------------------
  // The report could not be generated
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("sendPdfEmail: generation failure -> 500, NO mail, and the body says nothing was sent")
  void sendPdfEmail_generationFailure_returns500AndSendsNothing() {
    when(eventService.getAllEventsByDateIntervals(START, END)).thenReturn(List.of());
    when(eventService.generateEventsPdf(anyList(), anyLong(), anyLong()))
        .thenThrow(new ReportGenerationException("Failed to generate the events PDF",
            new NullPointerException("startTime is null")));

    ResponseEntity<String> response = eventController.sendPdfEmail(START, END, RECIPIENT);

    assertThat(response.getStatusCode().value()).isEqualTo(500);
    // The exact wording matters less than what it must NOT be: the old answer here was
    // 200 "Email sent successfully!".
    assertThat(response.getBody()).isNotEqualTo("Email sent successfully!");
    assertThat(response.getBody()).contains("report");
    assertThat(response.getBody()).contains("not");

    // Nothing was mailed. The 0-byte attachment cannot happen any more because the mail is never
    // composed at all.
    verifyNoInteractions(mailService);
  }

  @Test
  @DisplayName("sendPdfEmail: an EMPTY pdf is refused rather than mailed, even without an exception")
  void sendPdfEmail_emptyPdf_returns500AndSendsNothing() {
    // Belt and braces for the exact shape of the original defect. If some future path manages to
    // return a zero-byte stream without throwing, the controller still must not mail it and must
    // not call it a success.
    when(eventService.getAllEventsByDateIntervals(START, END)).thenReturn(List.of());
    when(eventService.generateEventsPdf(anyList(), anyLong(), anyLong()))
        .thenReturn(new ByteArrayOutputStream());

    ResponseEntity<String> response = eventController.sendPdfEmail(START, END, RECIPIENT);

    assertThat(response.getStatusCode().value()).isEqualTo(500);
    assertThat(response.getBody()).isNotEqualTo("Email sent successfully!");
    verifyNoInteractions(mailService);
  }

  // -------------------------------------------------------------------------------------------
  // The report was fine but the mail was not
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("sendPdfEmail: a mail failure -> 500 with a DIFFERENT message from a generation failure")
  void sendPdfEmail_mailFailure_returns500WithItsOwnMessage() {
    when(eventService.getAllEventsByDateIntervals(START, END)).thenReturn(List.of());
    when(eventService.generateEventsPdf(anyList(), anyLong(), anyLong()))
        .thenReturn(pdfBytes("%PDF-1.4 real"));
    doThrow(new RuntimeException("smtp down"))
        .when(mailService).sendEventsPdfEmail(anyString(), any());

    ResponseEntity<String> response = eventController.sendPdfEmail(START, END, RECIPIENT);

    assertThat(response.getStatusCode().value()).isEqualTo(500);
    assertThat(response.getBody()).isNotEqualTo("Email sent successfully!");
    // Distinguishable from the generation failure: "the report could not be built" and "the report
    // was built but could not be delivered" are different problems for whoever has to fix it.
    assertThat(response.getBody()).isEqualTo("Error sending email");
  }

  // -------------------------------------------------------------------------------------------
  // delete
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("delete: delegates the id straight to the service")
  void delete_delegatesToService() {
    eventController.getAllEvents("evt-1");

    verify(eventService).deletePeriodicEventById("evt-1");
    verify(mailService, never()).sendEventsPdfEmail(anyString(), any());
  }

  private static ByteArrayOutputStream pdfBytes(String content) {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    out.writeBytes(content.getBytes(StandardCharsets.ISO_8859_1));
    return out;
  }
}
