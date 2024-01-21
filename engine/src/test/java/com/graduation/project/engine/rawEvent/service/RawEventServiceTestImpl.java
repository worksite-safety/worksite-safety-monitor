package com.graduation.project.engine.rawEvent.service;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.repository.EventRepository;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.model.converter.UserResponseDto2UserConverter;
import com.graduation.project.engine.user.model.response.UserResponseDto;
import com.graduation.project.engine.user.service.UserService;
import jakarta.mail.MessagingException;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Collections;
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class RawEventServiceTestImpl {

  @Mock
  private EventRepository eventRepository;
  @Mock
  private MailService mailService;

  @Mock
  private UserService userService;

  @Mock
  private UserResponseDto2UserConverter userResponseDto2UserConverter;

  @Value("${event.fall.threshold.value}")
  private int fallEventThreshold;

  @InjectMocks
  private RawEventService rawEventService;

  @Test
  void testListener_FallEvent() throws MessagingException {
    RawEvent fallEvent = new RawEvent();
    fallEvent.setEventType(EventNameEnum.FALL.name());
    fallEvent.setCameraName("Camera1");

    User user = new User();
    user.setId("user123");
    user.setEmail("test@example.com");
    user.setRole(Role.ADMIN);

    UserResponseDto userResponseDto = UserResponseDto.builder()
        .email("test@example.com")
        .role(Role.ADMIN)
        .build();

    when(userService.getAllUsers()).thenReturn(Collections.singletonList(userResponseDto));
    when(userResponseDto2UserConverter.convert(Collections.singletonList(userResponseDto)))
        .thenReturn(Collections.singletonList(user));

    rawEventService.listener(fallEvent);

    verify(mailService, times(1)).sendUrgentEventMail(eq(user), any(LocalDateTime.class),
        eq("Camera1"));
  }

  @Test
  void testListener_NoHelmetEvent_AboveThreshold() {
    RawEvent noHelmetEvent = new RawEvent();
    noHelmetEvent.setEventType(EventNameEnum.NO_HELMET.name());
    noHelmetEvent.setCameraName("Camera2");
    noHelmetEvent.setTimePeriod(BigDecimal.valueOf(fallEventThreshold + 1));

    rawEventService.listener(noHelmetEvent);

    verify(eventRepository, times(1)).save(any(Event.class));
  }
}
