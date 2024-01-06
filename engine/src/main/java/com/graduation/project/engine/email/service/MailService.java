package com.graduation.project.engine.email.service;

import com.graduation.project.engine.email.models.Mail;
import com.graduation.project.engine.user.model.User;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import lombok.RequiredArgsConstructor;
import lombok.SneakyThrows;
import org.springframework.beans.factory.annotation.Value;
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
  public void sendForgotPasswordEmail(User user, String hashedEmailUrl) throws MessagingException {

    MimeMessage mimeMessage = javaMailSender.createMimeMessage();
    MimeMessageHelper mimeMessageHelper = new MimeMessageHelper(mimeMessage, true, "UTF-8");

    mimeMessageHelper.setFrom(fromMail);
    mimeMessageHelper.setTo(user.getEmail());

    String subject =
        "Dear " + user.getFirstName() + " " + user.getLastName() + ", Reset Your Password";

    mimeMessageHelper.setSubject(subject);

    String resetPasswordLink = "http://localhost:3000/resetpassword?token=" + hashedEmailUrl;

    // Create an HTML message using a beautiful template
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
}
