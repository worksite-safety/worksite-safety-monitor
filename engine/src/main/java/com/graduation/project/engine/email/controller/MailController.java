package com.graduation.project.engine.email.controller;

import com.graduation.project.engine.email.models.Mail;
import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.user.model.User;
import java.time.LocalDateTime;
import lombok.SneakyThrows;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/mail")
public class MailController {

  @Autowired
  private MailService mailService;


  @PostMapping("/send/{mail}")
  @SneakyThrows
  public String sendMail(@PathVariable String mail) {

    User user = User.builder()
        .firstName("Aziz Can")
        .lastName("Güveli")
        .email(mail).build();
    mailService.sendUrgentEventMail(user, LocalDateTime.now(), "0");
    return "Successfuly mail sended !!";

  }

}