package com.graduation.project.engine.repository;

import com.graduation.project.engine.models.Token;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;
import java.util.Optional;

public interface TokenRepository extends MongoRepository<Token, String> {

    List<Token> findByUserIdAndExpiredFalseAndRevokedFalse(String id);
    Optional<Token> findByToken(String token);
    List<Token> findByUserId(String id);
}
