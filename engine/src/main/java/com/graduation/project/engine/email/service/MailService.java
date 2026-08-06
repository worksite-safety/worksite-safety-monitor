package com.graduation.project.engine.email.service;

import com.graduation.project.engine.user.model.User;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import lombok.SneakyThrows;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailService {

  private final JavaMailSender javaMailSender;

  private final String fromMail;

  /**
   * Origin of the React app - {@code app.frontend.base-url}, no path, no trailing slash.
   *
   * <p>This was the literal {@code "http://localhost:3000/change-password"} spelled into
   * {@link #sendForgotPasswordEmail}. A reset link is the one part of this system that is read
   * OUTSIDE it, in somebody's mail client, on a machine that is not the server - so "localhost"
   * names the recipient's own computer, where nothing is listening. Every reset mail from any
   * deployed instance was therefore delivered successfully and completely useless, and the server
   * had no way to notice: the address is only resolved by the browser, long after the send
   * succeeded.
   *
   * <p>A constructor argument rather than a {@code @Value} field for the same reason the secrets
   * are: the value is validated once, at startup, so a blank or malformed origin stops the context
   * instead of producing dead links until somebody reports one.
   */
  private final String frontendBaseUrl;

  public MailService(JavaMailSender javaMailSender,
      @Value("${spring.mail.username}") String fromMail,
      @Value("${app.frontend.base-url}") String frontendBaseUrl) {
    this.javaMailSender = javaMailSender;
    this.fromMail = fromMail;

    if (frontendBaseUrl == null || frontendBaseUrl.isBlank()) {
      throw new IllegalStateException(
          "app.frontend.base-url is empty. Set it to the origin the frontend is served from, "
              + "e.g. https://safety.example.com.");
    }
    // Normalised here, once, so callers can concatenate a path beginning with '/' without any of
    // them having to know whether the configured value ended in one. "…example.com/" and
    // "…example.com" must not produce links that differ by a double slash.
    this.frontendBaseUrl = frontendBaseUrl.trim().replaceAll("/+$", "");
  }

  public void sendUrgentEventMail(User user, LocalDateTime detectionTimestamp,
      String cameraName) throws MessagingException {
    MimeMessage mimeMessage = javaMailSender.createMimeMessage();
    MimeMessageHelper mimeMessageHelper = new MimeMessageHelper(mimeMessage, true, "UTF-8");

    mimeMessageHelper.setFrom(fromMail);
    mimeMessageHelper.setTo(user.getEmail());

    String subject = "Dear " + user.getFirstName() + " " + user.getLastName()
        + " Fall Event Detected at Worksite " + " from Camera: " + cameraName;

    mimeMessageHelper.setSubject(subject);

    DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm");
    String formattedTimestamp = detectionTimestamp.format(formatter);

    String htmlContent = "<html>"
        + "<head>"
        + "<style>"
        + "body {font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #F5F5F5;}"
        + ".container {margin: auto; width: 80%; padding: 20px; background-color: #FFFFFF; box-shadow: 0px 0px 10px 0px rgba(0,0,0,0.1);}"
        + ".header {background-color: #9c1e24; padding: 20px; text-align: center; color: #FFFFFF; font-size: 24px;}"
        + ".content {padding: 20px;}"
        + ".footer {background-color: #F5F5F5; padding: 20px; text-align: center; font-size: 12px; color: #666666;}"
        + "</style>"
        + "</head>"
        + "<body>"
        + "<div class='container'>"
        + "<div class='header'><h1>" + subject + "</h1></div>"
        + "<p>Detection Time: " + formattedTimestamp + "</p>"
        + "<p>User Notification: " + user.getFirstName() + " " + user.getLastName() + "</p>"
        + "<p>Camera: " + cameraName + "</p></div>"
        + "<div class='footer'><h1 style='color: red;'>If There is an Emergency Call 911</h1></div>"
        + "</div>"
        + "</body>"
        + "</html>";

    mimeMessageHelper.setText(htmlContent, true);

    javaMailSender.send(mimeMessage);
  }

  @SneakyThrows
  public void sendForgotPasswordEmail(User user, String hashedEmailUrl) {

    MimeMessage mimeMessage = javaMailSender.createMimeMessage();
    MimeMessageHelper mimeMessageHelper = new MimeMessageHelper(mimeMessage, true, "UTF-8");

    mimeMessageHelper.setFrom(fromMail);
    mimeMessageHelper.setTo(user.getEmail());

    String subject =
        "Dear " + user.getFirstName() + " " + user.getLastName() + ", Reset Your Password";

    mimeMessageHelper.setSubject(subject);

    // The token is standard-alphabet Base64 (PasswordService.encrypt), which contains '+', '/'
    // and '=' - none of which survive a query string unescaped. '+' is the worst of them: it is
    // the query-string encoding of a space, so a reader cannot tell an intended '+' from a space,
    // and 49% of tokens produced by this key contain at least one.
    //
    // Encoded HERE, at the interpolation point, rather than by changing encrypt() to a URL-safe
    // alphabet. Encoding is a transport concern: the token's bytes are untouched, so the pinned
    // ciphertext contract in PasswordServiceTest holds, decrypt() keeps accepting exactly what it
    // always accepted, and every link already sitting in someone's inbox still resolves. Moving
    // encrypt() to Base64.getUrlEncoder() would instead change what the tokens ARE, requiring
    // decrypt() to straddle two alphabets forever to avoid invalidating those outstanding links.
    //
    // URLEncoder, not UriUtils.encodeQueryParam: '+' is an RFC 3986 sub-delimiter and therefore
    // *legal* in a query, so the RFC-correct encoder leaves it exactly as it is - which is the
    // one character that had to change.
    String resetPasswordLink = frontendBaseUrl + "/change-password?token="
        + URLEncoder.encode(hashedEmailUrl, StandardCharsets.UTF_8);

    String htmlContent = "<html>"
        + "<head>"
        + "<style>"
        + "body {font-family: Arial, sans-serif; margin: 0; padding: 0;}"
        + ".container {margin: auto; width: 80%; padding: 20px;}"
        + ".header {background-color: #f2f2f2; padding: 20px; text-align: center;}"
        + ".content {padding: 20px;}"
        + ".footer {background-color: #f2f2f2; padding: 20px; text-align: center;}"
        + ".button {background-color: #008CBA; border: none; color: white; padding: 15px 32px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 5px;}"
        + "</style>"
        + "</head>"
        + "<body>"
        + "<div class='container'>"
        + "<div class='header'><h2>Password Reset Request</h2></div>"
        + "<div class='content'>"
        + "<p>Dear " + user.getFirstName() + " " + user.getLastName() + ",</p>"
        + "<p>You have requested to reset your password. Click the button below to reset your password:</p>"
        + "<a href='" + resetPasswordLink + "' class='button'>Reset Password</a>"
        + "<p>If you didn't request this change, you can ignore this email.</p>"
        + "</div>"
        + "<div class='footer'>"
        // "© 2024 Code Runners Inc. All rights reserved." was wrong in three ways at once, in the
        // one message this system sends to somebody who has not logged in: no such company
        // exists, the year stopped being right in 2025, and "all rights reserved" is
        // the opposite of what the AGPL grant says. Copyright itself is real and is held jointly
        // by the contributors, so the years and the holder are taken from NOTICE verbatim rather
        // than restated, which is what stops the two drifting apart again.
        + "<p>&copy; 2023-2026 the Worksite Safety Monitor contributors. "
        + "Licensed under AGPL-3.0-or-later.</p>"
        + "</div>"
        + "</div>"
        + "</body>"
        + "</html>";

    mimeMessageHelper.setText(htmlContent, true);

    javaMailSender.send(mimeMessage);
  }

  @SneakyThrows
  public void sendEventsPdfEmail(String recipient, byte[] pdfData) {
    MimeMessage mimeMessage = javaMailSender.createMimeMessage();
    MimeMessageHelper mimeMessageHelper = new MimeMessageHelper(mimeMessage, true, "UTF-8");

    mimeMessageHelper.setFrom(fromMail);
    mimeMessageHelper.setTo(recipient);

    String subject = "Events Data PDF Attachment";
    mimeMessageHelper.setSubject(subject);

    String htmlContent = "Please find attached the PDF containing events data.";

    mimeMessageHelper.setText(htmlContent, true);
    mimeMessageHelper.addAttachment("events_data.pdf", new ByteArrayResource(pdfData));

    javaMailSender.send(mimeMessage);
  }
}
