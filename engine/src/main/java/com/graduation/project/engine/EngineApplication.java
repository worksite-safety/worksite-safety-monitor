package com.graduation.project.engine;

import com.graduation.project.engine.dto.converter.UserResponseDto2UserConverter;
import com.graduation.project.engine.dto.request.RegisterRequestDto;
import com.graduation.project.engine.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

import java.util.concurrent.atomic.AtomicBoolean;

@SpringBootApplication
@EnableMongoRepositories
public class EngineApplication implements CommandLineRunner {


    @Autowired
    UserService repository;
    @Autowired
    UserResponseDto2UserConverter userResponseDto2UserConverter;

    public static void main(String[] args) {
        SpringApplication.run(EngineApplication.class, args);
    }

    @Override
    public void run(String... args) {
        createEnv();
    }

    //CREATE
    void createEnv() {
        System.out.println("Data creation started...");
        AtomicBoolean isExists = new AtomicBoolean(false);
        repository.getAllUsers().forEach(userResponseDto -> {
            if (userResponseDto != null) {
                if (userResponseDto.getEmail().equals("emre@test.com")) {
                    isExists.set(true);
                }
            }
        });

        if (!isExists.get()) {
            repository.register(RegisterRequestDto.builder().email("emre@test.com").password("1").firstName("emre").lastName("yilmaz").build());
        }

        System.out.println("Data creation complete...");
    }
}
