package com.graduation.project.engine.service;

import com.graduation.project.engine.models.RawEvent;
import com.graduation.project.engine.repository.RawEventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class RawEventService {

    private final RawEventRepository rawEventRepository;


    public List<RawEvent> getAllRawEvents() {
        return rawEventRepository.findAll();
    }
}
