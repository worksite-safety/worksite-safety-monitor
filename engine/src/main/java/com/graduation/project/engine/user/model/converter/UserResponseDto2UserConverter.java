package com.graduation.project.engine.user.model.converter;

import com.graduation.project.engine.user.model.response.UserResponseDto;
import com.graduation.project.engine.user.model.User;
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