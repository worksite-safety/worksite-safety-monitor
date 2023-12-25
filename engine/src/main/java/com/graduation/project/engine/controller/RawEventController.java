package com.graduation.project.engine.controller;

import com.graduation.project.engine.models.RawEvent;
import com.graduation.project.engine.service.RawEventService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/raw-event")
@RequiredArgsConstructor
@CrossOrigin
public class RawEventController {

    private final RawEventService rawEventService;

    @GetMapping()
    public List<RawEvent> getAllRawEvents(){
        return rawEventService.getAllRawEvents();
    }


}
