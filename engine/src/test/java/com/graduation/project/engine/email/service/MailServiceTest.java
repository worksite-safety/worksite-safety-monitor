package com.graduation.project.engine.email.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import java.io.InputStream;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Characterization tests for {@link MailService}.
 *
 * <p>{@link JavaMailSender} is mocked and handed a real, session-less {@link MimeMessage}, so the
 * built message can be inspected without an SMTP server.
 *
 * <p>Deliberately NOT pinned: the HTML bodies. They are cosmetic and a later slice edits them.
 * What is pinned is the addressing, the subject line (which carries the camera name operators
 * triage on) and the shape of the password-reset link, because those are contracts other things
 * depend on.
 */
@ExtendWith(MockitoExtension.class)
class MailServiceTest {

  private static final String FROM = "worksite-noreply@example.com";

  @Mock
  private JavaMailSender javaMailSender;

  @InjectMocks
  private MailService mailService;

  @Captor
  private ArgumentCaptor<MimeMessage> messageCaptor;

  @BeforeEach
  void setUp() {
    // fromMail is @Value-injected, not a constructor parameter, so it stays null in a unit test.
    ReflectionTestUtils.setField(mailService, "fromMail", FROM);
    when(javaMailSender.createMimeMessage())
        .thenReturn(new MimeMessage(Session.getInstance(new Properties())));
  }

  @Test
  @DisplayName("urgent event mail: addressed from the configured account to the user")
  void urgentEventMail_addressing() throws Exception {
    mailService.sendUrgentEventMail(user("Ada", "Lovelace", "ada@example.com"),
        LocalDateTime.of(2023, 11, 14, 9, 5), "Camera1");

    MimeMessage sent = capturedMessage();
    assertThat(sent.getFrom()).singleElement().hasToString(FROM);
    assertThat(sent.getRecipients(Message.RecipientType.TO))
        .singleElement().hasToString("ada@example.com");
    assertThat(sent.getRecipients(Message.RecipientType.CC)).isNull();
    assertThat(sent.getRecipients(Message.RecipientType.BCC)).isNull();
  }

  @Test
  @DisplayName("urgent event mail: the subject carries the camera name and the user's full name")
  void urgentEventMail_subject() throws Exception {
    mailService.sendUrgentEventMail(user("Ada", "Lovelace", "ada@example.com"),
        LocalDateTime.of(2023, 11, 14, 9, 5), "GateCam-7");

    String subject = capturedMessage().getSubject();
    assertThat(subject).contains("GateCam-7");
    assertThat(subject).contains("Ada Lovelace");
    assertThat(subject).contains("Fall Event Detected");
  }

  @Test
  @DisplayName("urgent event mail: body is sent as HTML, and shows the timestamp as dd/MM/yyyy HH:mm")
  void urgentEventMail_isHtmlAndFormatsTheTimestamp() throws Exception {
    mailService.sendUrgentEventMail(user("Ada", "Lovelace", "ada@example.com"),
        LocalDateTime.of(2023, 11, 14, 9, 5), "Camera1");

    // Only the timestamp format is asserted, not the surrounding markup.
    assertThat(textPartsOf(capturedMessage())).anyMatch(part -> part.contains("14/11/2023 09:05"));
  }

  @Test
  @DisplayName("forgot-password mail: the reset link is http://localhost:3000/change-password?token=<ciphertext>")
  void forgotPasswordMail_resetLinkShape() throws Exception {
    String token = "MZQJDqc5XqIXLMzs1s0xH5vuYocPc2b4HixySp4mBJQ=";

    mailService.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), token);

    // Hard-coded host and port, and the raw AES ciphertext is dropped into the query string
    // unescaped (note the trailing '=' padding). Both are pinned as-is.
    assertThat(textPartsOf(capturedMessage()))
        .anyMatch(part -> part.contains("http://localhost:3000/change-password?token=" + token));
  }

  @Test
  @DisplayName("forgot-password mail: addressing and subject")
  void forgotPasswordMail_addressingAndSubject() throws Exception {
    mailService.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), "tok");

    MimeMessage sent = capturedMessage();
    assertThat(sent.getFrom()).singleElement().hasToString(FROM);
    assertThat(sent.getRecipients(Message.RecipientType.TO))
        .singleElement().hasToString("ada@example.com");
    assertThat(sent.getSubject()).isEqualTo("Dear Ada Lovelace, Reset Your Password");
  }

  @Test
  @DisplayName("pdf mail: fixed subject, and the report is attached as events_data.pdf")
  void eventsPdfMail_subjectAndAttachment() throws Exception {
    byte[] pdf = "%PDF-1.4 pretend".getBytes();

    mailService.sendEventsPdfEmail("ops@example.com", pdf);

    MimeMessage sent = capturedMessage();
    assertThat(sent.getSubject()).isEqualTo("Events Data PDF Attachment");
    assertThat(sent.getRecipients(Message.RecipientType.TO))
        .singleElement().hasToString("ops@example.com");
    assertThat(attachmentNamesOf(sent)).containsExactly("events_data.pdf");
  }

  @Test
  @DisplayName("pdf mail: a ZERO-BYTE report is attached and sent without complaint")
  void eventsPdfMail_emptyReportIsStillSent() throws Exception {
    // Pairs with EventServiceTest#pdf_swallowsExceptionAndReturnsEmptyStream: when PDF
    // generation fails, EventController passes an empty byte[] straight through to here and
    // still answers "Email sent successfully!".
    mailService.sendEventsPdfEmail("ops@example.com", new byte[0]);

    assertThat(attachmentNamesOf(capturedMessage())).containsExactly("events_data.pdf");
  }

  // -------------------------------------------------------------------------------------------

  private MimeMessage capturedMessage() {
    verify(javaMailSender).send(messageCaptor.capture());
    return messageCaptor.getValue();
  }

  private static User user(String firstName, String lastName, String email) {
    return User.builder()
        .firstName(firstName)
        .lastName(lastName)
        .email(email)
        .role(Role.ADMIN)
        .build();
  }

  /** Every textual part of the (multipart) message, decoded. */
  private static List<String> textPartsOf(MimeMessage message) throws Exception {
    List<String> parts = new ArrayList<>();
    collectText(message.getContent(), parts);
    return parts;
  }

  private static void collectText(Object content, List<String> sink) throws Exception {
    if (content instanceof String text) {
      sink.add(text);
    } else if (content instanceof MimeMultipart multipart) {
      for (int i = 0; i < multipart.getCount(); i++) {
        collectText(multipart.getBodyPart(i).getContent(), sink);
      }
    } else if (content instanceof InputStream stream) {
      stream.close();
    }
  }

  private static List<String> attachmentNamesOf(MimeMessage message) throws Exception {
    List<String> names = new ArrayList<>();
    collectFileNames(message.getContent(), names);
    return names;
  }

  private static void collectFileNames(Object content, List<String> sink) throws Exception {
    if (content instanceof MimeMultipart multipart) {
      for (int i = 0; i < multipart.getCount(); i++) {
        BodyPart part = multipart.getBodyPart(i);
        if (part.getFileName() != null) {
          sink.add(part.getFileName());
        }
        collectFileNames(part.getContent(), sink);
      }
    }
  }
}
