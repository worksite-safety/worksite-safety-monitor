package com.graduation.project.engine.email.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;

import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import java.io.InputStream;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

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

  /**
   * The frontend origin these tests configure. Still {@code http://localhost:3000}, so every
   * assertion about the reset link below is byte-for-byte the one it was before - but it now
   * arrives as an ARGUMENT rather than as a constant compiled into {@link MailService}, which is
   * the whole change.
   */
  private static final String FRONTEND = "http://localhost:3000";

  @Mock
  private JavaMailSender javaMailSender;

  private MailService mailService;

  @Captor
  private ArgumentCaptor<MimeMessage> messageCaptor;

  @BeforeEach
  void setUp() {
    // Built by hand rather than with @InjectMocks + ReflectionTestUtils. fromMail used to be a
    // @Value field that stayed null in a unit test and had to be poked in reflectively; both it
    // and the frontend origin are constructor parameters now, so the collaborators this service
    // needs are simply passed to it and there is nothing left to reach into.
    mailService = new MailService(javaMailSender, FROM, FRONTEND);
    // lenient(): the constructor-validation tests below never send anything, so under the
    // extension's default strict stubbing this shared stub would be reported as unused and fail
    // them. It is shared because every OTHER test needs it.
    lenient().when(javaMailSender.createMimeMessage())
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
  @DisplayName("forgot-password mail: the reset link URL-ENCODES the token into the query string")
  void forgotPasswordMail_resetLinkShape() throws Exception {
    String token = "MZQJDqc5XqIXLMzs1s0xH5vuYocPc2b4HixySp4mBJQ=";

    mailService.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), token);

    // INVERTED. This previously asserted the RAW token was interpolated:
    //
    //     .anyMatch(part -> part.contains("http://localhost:3000/change-password?token=" + token));
    //
    // with the note "the raw AES ciphertext is dropped into the query string unescaped (note the
    // trailing '=' padding). Both are pinned as-is." Only the escaping changed then: the '='
    // padding became %3D.
    //
    // The note said "the host and port are still hard-coded and still pinned". They are not any
    // more - they come from app.frontend.base-url, which this test supplies as FRONTEND. The
    // expected string is unchanged because the configured value is unchanged, which is what makes
    // this a pure externalisation: same output, different source.
    assertThat(textPartsOf(capturedMessage()))
        .anyMatch(part -> part.contains(
            FRONTEND + "/change-password?token=MZQJDqc5XqIXLMzs1s0xH5vuYocPc2b4HixySp4mBJQ%3D"));
  }

  @Test
  @DisplayName("forgot-password mail: the link is built from the CONFIGURED origin, not localhost")
  void forgotPasswordMail_linkUsesTheConfiguredFrontendOrigin() throws Exception {
    // The test that says the value is genuinely configuration. Every other assertion in this class
    // uses http://localhost:3000, which is exactly the string that used to be hard-coded - so on
    // its own the suite could not tell a bound property from the old constant.
    MailService deployed =
        new MailService(javaMailSender, FROM, "https://safety.example.com");

    deployed.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), "tok");

    List<String> parts = textPartsOf(capturedMessage());
    assertThat(parts).anyMatch(
        part -> part.contains("https://safety.example.com/change-password?token=tok"));
    assertThat(parts).noneMatch(part -> part.contains("localhost"));
  }

  @Test
  @DisplayName("forgot-password mail: a trailing slash on the base URL does not double up")
  void forgotPasswordMail_trailingSlashOnTheBaseUrlIsNormalised() throws Exception {
    // "https://safety.example.com/" is the form somebody will inevitably put in the environment
    // variable, and "…com//change-password" is a link some proxies and routers will not serve.
    MailService deployed =
        new MailService(javaMailSender, FROM, "https://safety.example.com/");

    deployed.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), "tok");

    assertThat(textPartsOf(capturedMessage()))
        .anyMatch(part -> part.contains("https://safety.example.com/change-password?token=tok"))
        .noneMatch(part -> part.contains("//change-password"));
  }

  @Test
  @DisplayName("a blank frontend origin stops the service being built, rather than sending dead links")
  void blankFrontendBaseUrlIsRejectedAtConstruction() {
    // Startup, not send-time. A dead reset link fails in the recipient's browser, hours later and
    // somewhere the server cannot see; there is no error to catch and nothing to log.
    assertThatThrownBy(() -> new MailService(javaMailSender, FROM, "  "))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("app.frontend.base-url is empty");
  }

  @Test
  @DisplayName("forgot-password mail: a '+' in the token is escaped, so it cannot arrive as a space")
  void forgotPasswordMail_plusInTokenIsEscaped() throws Exception {
    // A genuine ciphertext from this exact key, for the address user3@example.com. '+' is an
    // ordinary character of the standard Base64 alphabet and it is also the query-string encoding
    // of a space, so interpolating it raw makes the two indistinguishable at the receiver.
    // Measured over 20 000 synthetic addresses through the real PasswordService: 49.0% of tokens
    // contain at least one '+'. This is the coin-flip that decides whether a reset link works.
    String token = "LjjG0G+jeLbYbdb2MWYddDYBCiaC4P1lQvk3g0V2Q58=";

    mailService.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), token);

    List<String> parts = textPartsOf(capturedMessage());
    assertThat(parts).anyMatch(part -> part.contains(
        "?token=LjjG0G%2BjeLbYbdb2MWYddDYBCiaC4P1lQvk3g0V2Q58%3D"));
    assertThat(parts).noneMatch(part -> part.contains("?token=LjjG0G+"));
  }

  @Test
  @DisplayName("forgot-password mail: the emitted link decodes back to EXACTLY the token handed in")
  void forgotPasswordMail_linkDecodesBackToTheOriginalToken() throws Exception {
    // The contract that actually matters, stated end to end rather than as a string shape: what a
    // standards-compliant reader pulls out of the query string must be byte-for-byte what
    // UserService encrypted, because PasswordService.decrypt gets no second chance at it. Every
    // character Base64 can produce is exercised, '+' and '/' included.
    String token = "LjjG0G+jeL/Ybdb2MWYddDYBCiaC4P1lQvk3g0V2Q58=";

    mailService.sendForgotPasswordEmail(user("Ada", "Lovelace", "ada@example.com"), token);

    assertThat(URLDecoder.decode(tokenQueryParameterOf(capturedMessage()), StandardCharsets.UTF_8))
        .isEqualTo(token);
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

  /**
   * The raw, still-encoded value of the {@code token} query parameter in the reset link, pulled
   * out of the {@code href}. Deliberately not a snapshot of the surrounding HTML - only the one
   * value whose exact bytes are a contract.
   */
  private static String tokenQueryParameterOf(MimeMessage message) throws Exception {
    Matcher matcher = Pattern
        .compile("href='" + Pattern.quote(FRONTEND) + "/change-password\\?token=([^']*)'")
        .matcher(String.join("\n", textPartsOf(message)));
    assertThat(matcher.find()).as("the mail must contain a reset link").isTrue();
    return matcher.group(1);
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
