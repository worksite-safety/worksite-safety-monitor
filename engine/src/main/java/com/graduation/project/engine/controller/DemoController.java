package com.graduation.project.engine.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController("/demo")
public class DemoController {

    @GetMapping("/aziz")
    public String getDemo(){
        return "Hello";
    }

    @GetMapping("/authreq")
    public String getAuthreq(){
        return "HelloAuth";
    }




}
