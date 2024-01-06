package com.graduation.project.engine.email.controller;

import com.graduation.project.engine.email.models.MailStructure;
import com.graduation.project.engine.email.service.EmailService;
import jakarta.mail.MessagingException;
import lombok.SneakyThrows;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/mail")
public class MailController {

  @Autowired
  private EmailService emailService;


  @PostMapping("/send/{mail}")
  @SneakyThrows
  public String sendMail(@PathVariable String mail, @RequestBody MailStructure mailStructure) {

    emailService.sendMail(mail, mailStructure);
    return "Successfuly mail sended !!";

  }

}