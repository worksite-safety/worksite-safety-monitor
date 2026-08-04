package com.graduation.project.engine.email.service;

import com.graduation.project.engine.user.model.User;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import lombok.RequiredArgsConstructor;
import lombok.SneakyThrows;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class MailService {

  private final JavaMailSender javaMailSender;

  @Value("${spring.mail.username}")
  private String fromMail;

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
    String resetPasswordLink = "http://localhost:3000/change-password?token="
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
        + "<p>&copy; 2024 Code Runners Inc. All rights reserved.</p>"
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
