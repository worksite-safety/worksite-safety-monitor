package com.graduation.project.engine.rawEvent.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
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
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Characterization tests for {@link RawEventService#listener(RawEvent)}.
 *
 * <p>These pin CURRENT behaviour, including behaviour that looks wrong (see
 * {@code noHelmet_exactlyAtThreshold_isNotPersisted}). They are not a fix.
 *
 * <p>Deliberately a pure unit test: the previous {@code RawEventServiceTestImpl} combined
 * {@code @SpringBootTest} with bare {@code @Mock}/{@code @InjectMocks} and no Mockito
 * initialisation at all, so every mock field was null and the service under test was null too.
 */
@ExtendWith(MockitoExtension.class)
class RawEventServiceTest {

  private static final int FALL_EVENT_THRESHOLD = 3;

  @Mock
  private EventRepository eventRepository;

  @Mock
  private MailService mailService;

  @Mock
  private UserService userService;

  @Mock
  private UserResponseDto2UserConverter userResponseDto2UserConverter;

  @InjectMocks
  private RawEventService rawEventService;

  @Captor
  private ArgumentCaptor<Event> eventCaptor;

  @Captor
  private ArgumentCaptor<User> userCaptor;

  @BeforeEach
  void setUp() {
    // fallEventThreshold is an @Value-injected field, not a constructor parameter, so it
    // stays 0 in a pure unit test. A later slice moves it into the constructor.
    ReflectionTestUtils.setField(rawEventService, "fallEventThreshold", FALL_EVENT_THRESHOLD);
  }

  @Test
  @DisplayName("FALL: mails every user in the system")
  void fallEvent_mailsEveryUser() throws Exception {
    RawEvent fallEvent = rawEvent(EventNameEnum.FALL, null);

    List<UserResponseDto> dtos = Arrays.asList(
        userDto("first@example.com"),
        userDto("second@example.com"));
    List<User> users = Arrays.asList(
        user("first@example.com"),
        user("second@example.com"));

    when(userService.getAllUsers()).thenReturn(dtos);
    when(userResponseDto2UserConverter.convert(dtos)).thenReturn(users);

    rawEventService.listener(fallEvent);

    verify(mailService, times(2))
        .sendUrgentEventMail(userCaptor.capture(), any(LocalDateTime.class), eq("Camera1"));

    List<String> mailedTo = userCaptor.getAllValues().stream()
        .map(User::getEmail)
        .collect(Collectors.toList());
    assertEquals(Arrays.asList("first@example.com", "second@example.com"), mailedTo);
  }

  @Test
  @DisplayName("FALL: is persisted (it is not a NO_HELMET/NO_JACKET event, so it hits the else branch)")
  void fallEvent_isPersisted() throws Exception {
    RawEvent fallEvent = rawEvent(EventNameEnum.FALL, null);

    when(userService.getAllUsers()).thenReturn(List.of());
    when(userResponseDto2UserConverter.convert(List.<UserResponseDto>of())).thenReturn(List.of());

    rawEventService.listener(fallEvent);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.FALL.name(), eventCaptor.getValue().getEventType());
    assertEquals("Camera1", eventCaptor.getValue().getCameraName());
  }

  @Test
  @DisplayName("NO_HELMET: above the threshold is persisted")
  void noHelmet_aboveThreshold_isPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_HELMET,
        BigDecimal.valueOf(FALL_EVENT_THRESHOLD + 1));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.NO_HELMET.name(), eventCaptor.getValue().getEventType());
    verifyNoInteractions(mailService);
  }

  @Test
  @DisplayName("NO_HELMET: exactly at the threshold is NOT persisted (the code uses a strict >)")
  void noHelmet_exactlyAtThreshold_isNotPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_HELMET, BigDecimal.valueOf(FALL_EVENT_THRESHOLD));

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
  }

  @Test
  @DisplayName("NO_JACKET: below the threshold is NOT persisted")
  void noJacket_belowThreshold_isNotPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_JACKET,
        BigDecimal.valueOf(FALL_EVENT_THRESHOLD - 1));

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
  }

  @Test
  @DisplayName("NO_JACKET: above the threshold is persisted")
  void noJacket_aboveThreshold_isPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_JACKET,
        BigDecimal.valueOf(FALL_EVENT_THRESHOLD + 1));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.NO_JACKET.name(), eventCaptor.getValue().getEventType());
  }

  @Test
  @DisplayName("ARMS_UP: persisted unconditionally, no mail")
  void armsUp_isPersisted() {
    RawEvent event = rawEvent(EventNameEnum.ARMS_UP, null);

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.ARMS_UP.name(), eventCaptor.getValue().getEventType());
    verifyNoInteractions(mailService, userService, userResponseDto2UserConverter);
  }

  @Test
  @DisplayName("FRONT_BEND: persisted unconditionally, no mail")
  void frontBend_isPersisted() {
    RawEvent event = rawEvent(EventNameEnum.FRONT_BEND, null);

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.FRONT_BEND.name(), eventCaptor.getValue().getEventType());
    verifyNoInteractions(mailService, userService, userResponseDto2UserConverter);
  }

  @Test
  @DisplayName("unknown eventType: persisted UNCONDITIONALLY via the else branch, threshold ignored")
  void unknownEventType_isPersistedUnconditionally() {
    // Nothing validates eventType against EventNameEnum. Anything the Python detector puts on
    // the topic that is not NO_HELMET/NO_JACKET falls through to the else branch and is stored,
    // even with a timePeriod far below the threshold that would have rejected a known periodic
    // event. A later slice deliberately inverts this to reject-by-default.
    RawEvent event = rawEvent("SOMETHING_THE_BACKEND_HAS_NEVER_HEARD_OF", BigDecimal.ZERO);

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals("SOMETHING_THE_BACKEND_HAS_NEVER_HEARD_OF",
        eventCaptor.getValue().getEventType());
    verifyNoInteractions(mailService, userService, userResponseDto2UserConverter);
  }

  @Test
  @DisplayName("unknown eventType is stored even though no query can ever read it back")
  void unknownEventType_isWriteOnly() {
    // EventService only ever queries findAllByEventTypeIn([the five known names], ...), so these
    // documents accumulate in the "event" collection and are invisible to every endpoint.
    rawEventService.listener(rawEvent("TYPO_IN_THE_DETECTOR", null));

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals("TYPO_IN_THE_DETECTOR", eventCaptor.getValue().getEventType());
  }

  @Test
  @DisplayName("null eventType: NullPointerException escapes the listener (poison-pill message)")
  void nullEventType_throwsNullPointerException() {
    // RawEvent is @JsonIgnoreProperties(ignoreUnknown = true), so a payload that simply omits
    // eventType deserialises with a null field and blows up on the first .equals(...) call.
    RawEvent event = rawEvent((String) null, null);

    assertThrows(NullPointerException.class, () -> rawEventService.listener(event));

    verify(eventRepository, never()).save(any(Event.class));
  }

  private static RawEvent rawEvent(EventNameEnum type, BigDecimal timePeriod) {
    return rawEvent(type.name(), timePeriod);
  }

  private static RawEvent rawEvent(String eventType, BigDecimal timePeriod) {
    RawEvent rawEvent = new RawEvent();
    rawEvent.setEventType(eventType);
    rawEvent.setCameraName("Camera1");
    rawEvent.setConfidencePercentage(BigDecimal.valueOf(90));
    rawEvent.setIsProcessed("false");
    rawEvent.setStartTime(1_700_000_000_000L);
    rawEvent.setTimePeriod(timePeriod);
    return rawEvent;
  }

  private static UserResponseDto userDto(String email) {
    return UserResponseDto.builder()
        .email(email)
        .role(Role.ADMIN)
        .build();
  }

  private static User user(String email) {
    return User.builder()
        .email(email)
        .role(Role.ADMIN)
        .build();
  }
}
