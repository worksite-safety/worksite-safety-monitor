package com.graduation.project.engine.email.service;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

  @Value("${kafka.mail.host}")
  private String mailHost;

  @Value("${kafka.mail.port}")
  private int mailPort;

  @Value("${kafka.mail.username}")
  private String mailUsername;

  @Value("${kafka.mail.password}")
  private String mailPassword;

  @Bean
  public JavaMailSender javaMailSender() {
    JavaMailSenderImpl mailSender = new JavaMailSenderImpl();
    mailSender.setHost(mailHost);
    mailSender.setPort(mailPort);
    mailSender.setUsername(mailUsername);
    mailSender.setPassword(mailPassword);

    // Additional properties if needed
    Properties properties = mailSender.getJavaMailProperties();
    properties.put("mail.smtp.auth", "true");
    properties.put("mail.smtp.starttls.enable", "true");

    return mailSender;
  }
}