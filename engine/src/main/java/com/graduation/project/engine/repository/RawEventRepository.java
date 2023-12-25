package com.graduation.project.engine.repository;

import com.graduation.project.engine.models.RawEvent;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface RawEventRepository extends MongoRepository<RawEvent, String> {



}
