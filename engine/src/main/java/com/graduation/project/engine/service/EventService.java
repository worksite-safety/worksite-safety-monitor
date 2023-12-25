package com.graduation.project.engine.service;

import com.graduation.project.engine.dto.response.EventResponseDto;
import com.graduation.project.engine.models.Event;
import com.graduation.project.engine.repository.EventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class EventService {

    private final EventRepository eventRepository;

    public List<Event> getAllEvents() {

        return eventRepository.findAll();

    }

    public List<Event> getAllByEventType(String eventType){

        return eventRepository.findAllByEventPrediction(eventType);
    }

}
