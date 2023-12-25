package com.graduation.project.engine.repository;

import com.graduation.project.engine.models.Event;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface EventRepository extends MongoRepository<Event, String> {

    List<Event> findAllByEventPrediction(String eventPrediction);

}
