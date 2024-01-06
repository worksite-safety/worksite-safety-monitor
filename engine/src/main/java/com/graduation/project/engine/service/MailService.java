package com.graduation.project.engine.service;

import com.graduation.project.engine.models.MailStructure;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailService {

    @Autowired
    private JavaMailSenderImpl javaMailSender;

    @Value("$(spring.mail.username)")
    private String fromMail;

    public MailService(JavaMailSenderImpl javaMailSender) {
        this.javaMailSender = javaMailSender;
    }
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
