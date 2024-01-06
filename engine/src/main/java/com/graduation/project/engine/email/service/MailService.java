package com.graduation.project.engine.email.service;

import com.graduation.project.engine.email.models.Mail;
import com.graduation.project.engine.user.model.User;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import lombok.RequiredArgsConstructor;
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
        + ".header {background-color: #4CAF50; padding: 20px; text-align: center; color: #FFFFFF; font-size: 24px;}"
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
}
