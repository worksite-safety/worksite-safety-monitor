package com.graduation.project.engine.email.service;

import com.graduation.project.engine.email.models.MailStructure;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class EmailService {

    private final JavaMailSender javaMailSender;

    @Value("$(spring.mail.username)")
    private String fromMail;

    public void sendMail(String mail, MailStructure mailStructure) throws MessagingException {
        MimeMessage mimeMessage = javaMailSender.createMimeMessage();
        MimeMessageHelper mimeMessageHelper = new MimeMessageHelper(mimeMessage, true);

        mimeMessageHelper.setFrom(fromMail);
        mimeMessageHelper.setTo(mail);
        mimeMessageHelper.setSubject(mailStructure.getSubject());
        mimeMessageHelper.setText(mailStructure.getMessage());

        javaMailSender.send(mimeMessage);
    }
}
