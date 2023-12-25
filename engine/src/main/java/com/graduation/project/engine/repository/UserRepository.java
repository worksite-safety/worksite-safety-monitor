package com.graduation.project.engine.repository;

import com.graduation.project.engine.models.User;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

import java.util.Optional;

public interface UserRepository extends MongoRepository<User, String> {
    @Query("{email:'?0'}")
    Optional<User> findByEmail (String email);
}
