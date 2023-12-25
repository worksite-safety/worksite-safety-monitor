package com.graduation.project.engine.dto.converter;

import com.graduation.project.engine.dto.response.UserResponseDto;
import com.graduation.project.engine.models.User;
import org.springframework.stereotype.Component;

@Component
public class UserResponseDto2UserConverter {

    public User convert(UserResponseDto from){
        return new User(from.getUserId(),
                from.getFirstName(),
                from.getLastName(),
                from.getEmail(),
                from.getRole()
        );
    }

}