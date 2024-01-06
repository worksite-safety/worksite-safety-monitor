package com.graduation.project.engine.controller;

import com.graduation.project.engine.models.MailStructure;
import com.graduation.project.engine.service.MailService;
import jakarta.mail.MessagingException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/mail")
public class MailController {

    @Autowired
    private MailService mailService;


    @PostMapping("/send/{mail}")
    public String sendMail(@PathVariable String mail, @RequestBody MailStructure mailStructure) throws MessagingException, MessagingException {

        mailService.sendMail(mail,mailStructure);
        return "Successfuly mail sended !!";

    }

}