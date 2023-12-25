package com.graduation.project.engine.dto.converter;

import com.graduation.project.engine.dto.response.UserResponseDto;
import com.graduation.project.engine.models.User;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.stream.Collectors;

@Component
public class User2UserResponseDtoConverter {

    public UserResponseDto convert(User user) {
        return new UserResponseDto(user.getId(),
                user.getEmail(),
                user.getFirstName(),
                user.getLastName(),
                user.getRole(),
                user.isEnabled()
        );
    }

    public List<UserResponseDto> convert(List<User> users) {
        return users.stream().map(user -> new UserResponseDto(user.getId(),
                user.getEmail(),
                user.getFirstName(),
                user.getLastName(),
                user.getRole(),
                user.isEnabled())).collect(Collectors.toList());
    }

}
