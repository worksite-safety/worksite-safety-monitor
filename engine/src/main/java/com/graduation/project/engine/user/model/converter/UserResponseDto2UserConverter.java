package com.graduation.project.engine.user.model.converter;

import com.graduation.project.engine.user.model.response.UserResponseDto;
import com.graduation.project.engine.user.model.User;
import java.util.List;
import java.util.stream.Collectors;
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
    public List<User> convert(List<UserResponseDto> users) {
        return users.stream().map(userDto -> User.builder()
                .email(userDto.getEmail())
                .firstName(userDto.getFirstName())
                .lastName(userDto.getLastName())
                .role(userDto.getRole())
                .build())
            .collect(Collectors.toList());
    }

}