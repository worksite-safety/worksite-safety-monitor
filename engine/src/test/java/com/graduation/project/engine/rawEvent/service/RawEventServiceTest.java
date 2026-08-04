package com.graduation.project.engine.rawEvent.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.model.Event;
import com.graduation.project.engine.event.model.EventNameEnum;
import com.graduation.project.engine.event.repository.EventRepository;
import com.graduation.project.engine.rawEvent.model.PeriodicInputUnit;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.model.converter.UserResponseDto2UserConverter;
import com.graduation.project.engine.user.model.response.UserResponseDto;
import com.graduation.project.engine.user.service.UserService;
import jakarta.mail.MessagingException;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailSendException;
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

  /**
   * The threshold, in the unit it is now declared in. {@code event.periodic.min-duration-ms}
   * replaces {@code event.fall.threshold.value}: the old name claimed to be about FALL while it
   * only ever gated NO_HELMET/NO_JACKET, and it carried no unit at all, which is exactly how a
   * seconds-valued {@code 3} came to be compared against milliseconds in production.
   */
  private static final long MIN_PERIODIC_DURATION_MS = 3_000L;

  /**
   * The same threshold expressed in the unit the pre-rewrite detector sends. Every threshold
   * assertion that predates this slice is written in terms of this constant and is unchanged:
   * under {@code SECONDS} a value of 3 still fails the check and 4 still passes it, because 3 s
   * normalises to 3000 ms and {@code 3000 > 3000} is false. The verdicts are identical; only the
   * unit the service compares in has moved.
   */
  private static final int THRESHOLD_SECONDS = 3;

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

  /**
   * Captures what the service logs. Two of the contracts here are log lines and nothing else -
   * a dropped unrecognised event and a mail that could not be sent both leave no other trace -
   * so "it logged exactly one WARNING" is the assertion, not a nicety.
   */
  private ListAppender<ILoggingEvent> logs;

  @BeforeEach
  void setUp() {
    // Both are @Value-injected fields rather than constructor parameters, so they stay 0/null in
    // a pure unit test. SECONDS is the production default: it describes the detector that is in
    // the field today, so this is the configuration the engine actually runs with until the
    // rewritten detector ships.
    ReflectionTestUtils.setField(rawEventService, "minPeriodicDurationMs",
        MIN_PERIODIC_DURATION_MS);
    ReflectionTestUtils.setField(rawEventService, "periodicInputUnit", PeriodicInputUnit.SECONDS);

    logs = new ListAppender<>();
    logs.start();
    serviceLogger().addAppender(logs);
  }

  @AfterEach
  void tearDown() {
    serviceLogger().detachAppender(logs);
    logs.stop();
  }

  private static ch.qos.logback.classic.Logger serviceLogger() {
    return (ch.qos.logback.classic.Logger) LoggerFactory.getLogger(RawEventService.class);
  }

  private List<ILoggingEvent> logsAt(Level level) {
    return new ArrayList<>(logs.list).stream().filter(e -> e.getLevel() == level).toList();
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

  // ---------------------------------------------------------------------------------------------
  // A failing mail server must not cost anyone else their notification, and must never cost the
  // event itself.
  //
  // sendUrgentEventMail throws MessagingException, the loop had no try/catch, and @SneakyThrows
  // rethrows it out of the listener - so ONE unreachable mailbox ended the loop, and because the
  // save sits after the loop, the FALL was never written to MongoDB either. A transient SMTP
  // outage silently deleted the safety record of a person falling over.
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("FALL: one user's mail failing does not stop the others being attempted")
  void fallEvent_oneMailFails_theRemainingUsersAreStillMailed() throws Exception {
    RawEvent fallEvent = rawEvent(EventNameEnum.FALL, null);

    List<UserResponseDto> dtos = Arrays.asList(
        userDto("first@example.com"), userDto("second@example.com"), userDto("third@example.com"));
    List<User> users = Arrays.asList(
        user("first@example.com"), user("second@example.com"), user("third@example.com"));

    when(userService.getAllUsers()).thenReturn(dtos);
    when(userResponseDto2UserConverter.convert(dtos)).thenReturn(users);

    // The middle recipient is the one whose mailbox rejects. Middle, not first or last, so that
    // the test distinguishes "kept going" from "happened to fail on the final iteration".
    doAnswer(invocation -> {
      User recipient = invocation.getArgument(0);
      if ("second@example.com".equals(recipient.getEmail())) {
        throw new MessagingException("SMTP 421 service not available");
      }
      return null;
    }).when(mailService)
        .sendUrgentEventMail(any(User.class), any(LocalDateTime.class), anyString());

    rawEventService.listener(fallEvent);

    verify(mailService, times(3))
        .sendUrgentEventMail(userCaptor.capture(), any(LocalDateTime.class), eq("Camera1"));
    assertEquals(
        Arrays.asList("first@example.com", "second@example.com", "third@example.com"),
        userCaptor.getAllValues().stream().map(User::getEmail).collect(Collectors.toList()),
        "every user must be attempted; the third proves the loop survived the second");

    // The failure is not swallowed in silence - it is the only trace an operator would ever get.
    assertEquals(1, logsAt(Level.ERROR).size(), "exactly one ERROR, for the one failed send");
    assertTrue(logsAt(Level.ERROR).get(0).getFormattedMessage().contains("second@example.com"),
        "the log must name the recipient that was not reached");
  }

  @Test
  @DisplayName("FALL: the event is STILL PERSISTED when every single mail fails")
  void fallEvent_isPersistedEvenWhenEveryMailFails() throws Exception {
    // The important half. Notifying is best-effort; recording that a fall happened is not.
    RawEvent fallEvent = rawEvent(EventNameEnum.FALL, null);

    List<UserResponseDto> dtos = Arrays.asList(
        userDto("first@example.com"), userDto("second@example.com"));
    List<User> users = Arrays.asList(user("first@example.com"), user("second@example.com"));

    when(userService.getAllUsers()).thenReturn(dtos);
    when(userResponseDto2UserConverter.convert(dtos)).thenReturn(users);
    doThrow(new MessagingException("connection refused"))
        .when(mailService)
        .sendUrgentEventMail(any(User.class), any(LocalDateTime.class), anyString());

    rawEventService.listener(fallEvent);

    verify(mailService, times(2))
        .sendUrgentEventMail(any(User.class), any(LocalDateTime.class), anyString());
    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.FALL.name(), eventCaptor.getValue().getEventType());
    assertEquals("Camera1", eventCaptor.getValue().getCameraName());
    assertEquals(2, logsAt(Level.ERROR).size(), "one ERROR per unreachable recipient");
  }

  @Test
  @DisplayName("FALL: an UNCHECKED mail failure is isolated too - that is the one a real SMTP outage throws")
  void fallEvent_uncheckedMailFailure_isAlsoIsolated() throws Exception {
    // MailService.sendUrgentEventMail declares MessagingException, but the call that actually
    // talks to the network - JavaMailSender.send - throws org.springframework.mail.MailException,
    // which is UNCHECKED and therefore absent from the method signature. A catch clause written
    // against the declared MessagingException alone would still let a refused connection abort
    // the loop and discard the event, i.e. it would fix the defect only for the failure mode that
    // does not happen in production. Hence this test, and hence catch(Exception) in the listener.
    RawEvent fallEvent = rawEvent(EventNameEnum.FALL, null);

    List<UserResponseDto> dtos = Arrays.asList(
        userDto("first@example.com"), userDto("second@example.com"));
    List<User> users = Arrays.asList(user("first@example.com"), user("second@example.com"));

    when(userService.getAllUsers()).thenReturn(dtos);
    when(userResponseDto2UserConverter.convert(dtos)).thenReturn(users);
    doThrow(new MailSendException("Mail server connection failed"))
        .when(mailService)
        .sendUrgentEventMail(any(User.class), any(LocalDateTime.class), anyString());

    rawEventService.listener(fallEvent);

    verify(mailService, times(2))
        .sendUrgentEventMail(any(User.class), any(LocalDateTime.class), anyString());
    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.FALL.name(), eventCaptor.getValue().getEventType());
  }

  @Test
  @DisplayName("NO_HELMET: above the threshold is persisted")
  void noHelmet_aboveThreshold_isPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_HELMET,
        BigDecimal.valueOf(THRESHOLD_SECONDS + 1));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.NO_HELMET.name(), eventCaptor.getValue().getEventType());
    verifyNoInteractions(mailService);
  }

  @Test
  @DisplayName("NO_HELMET: exactly at the threshold is NOT persisted (the code uses a strict >)")
  void noHelmet_exactlyAtThreshold_isNotPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_HELMET, BigDecimal.valueOf(THRESHOLD_SECONDS));

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
  }

  @Test
  @DisplayName("NO_JACKET: below the threshold is NOT persisted")
  void noJacket_belowThreshold_isNotPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_JACKET,
        BigDecimal.valueOf(THRESHOLD_SECONDS - 1));

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
  }

  @Test
  @DisplayName("NO_JACKET: above the threshold is persisted")
  void noJacket_aboveThreshold_isPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_JACKET,
        BigDecimal.valueOf(THRESHOLD_SECONDS + 1));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.NO_JACKET.name(), eventCaptor.getValue().getEventType());
  }

  // ---------------------------------------------------------------------------------------------
  // Unit normalisation on ingest (event.periodic.input-unit).
  //
  // The invariant these establish: whatever unit arrives on the topic, what reaches the repository
  // is ALWAYS milliseconds, and the threshold is ALWAYS compared in milliseconds. That is what
  // lets the detector and the engine deploy in either order without a silent window in which the
  // collection either fills with 33 ms flickers or goes completely empty.
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("SECONDS: an incoming 3 is 3000 ms, which does not clear a 3000 ms floor")
  void secondsInput_atThreshold_isNotPersisted() {
    RawEvent event = rawEvent(EventNameEnum.NO_HELMET, new BigDecimal("3"));

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
  }

  @Test
  @DisplayName("SECONDS: an incoming 4 clears the floor and is STORED AS 4000, not as 4")
  void secondsInput_aboveThreshold_isPersistedInMilliseconds() {
    RawEvent event = rawEvent(EventNameEnum.NO_HELMET, new BigDecimal("4"));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    // The whole point of the slice: the number that lands in MongoDB is normalised, so every
    // reader downstream of the collection deals in exactly one unit.
    assertEquals(0, eventCaptor.getValue().getTimePeriod().compareTo(new BigDecimal("4000")),
        "a 4 second window must be stored as 4000 milliseconds");
  }

  @Test
  @DisplayName("MILLIS: an incoming 3000 does not clear a 3000 ms floor (strict >, unchanged)")
  void millisInput_atThreshold_isNotPersisted() {
    ReflectionTestUtils.setField(rawEventService, "periodicInputUnit", PeriodicInputUnit.MILLIS);
    RawEvent event = rawEvent(EventNameEnum.NO_JACKET, new BigDecimal("3000"));

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
  }

  @Test
  @DisplayName("MILLIS: an incoming 3001 clears the floor and is stored unchanged as 3001")
  void millisInput_aboveThreshold_isPersistedUnchanged() {
    ReflectionTestUtils.setField(rawEventService, "periodicInputUnit", PeriodicInputUnit.MILLIS);
    RawEvent event = rawEvent(EventNameEnum.NO_JACKET, new BigDecimal("3001"));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(0, eventCaptor.getValue().getTimePeriod().compareTo(new BigDecimal("3001")),
        "under MILLIS the value must pass through untouched");
  }

  @Test
  @DisplayName("MILLIS: the 33 ms flicker from the differential run is rejected")
  void millisInput_theMeasuredFlicker_isRejected() {
    // The differential run over 986 frames produced jacket windows of 0, 200, 33 and 6500 ms.
    // Against the old seconds-valued `3` the middle two were stored; only the 6500 ms window is a
    // real violation. This pins the 33 ms case specifically, because it is the one that made the
    // defect visible.
    ReflectionTestUtils.setField(rawEventService, "periodicInputUnit", PeriodicInputUnit.MILLIS);

    rawEventService.listener(rawEvent(EventNameEnum.NO_JACKET, new BigDecimal("0")));
    rawEventService.listener(rawEvent(EventNameEnum.NO_JACKET, new BigDecimal("200")));
    rawEventService.listener(rawEvent(EventNameEnum.NO_JACKET, new BigDecimal("33")));

    verify(eventRepository, never()).save(any(Event.class));

    rawEventService.listener(rawEvent(EventNameEnum.NO_JACKET, new BigDecimal("6500")));

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(0, eventCaptor.getValue().getTimePeriod().compareTo(new BigDecimal("6500")));
  }

  @Test
  @DisplayName("the comparison uses longValue(): a 34.7 day window does not wrap to a negative int")
  void durationBeyondIntRange_isNotSilentlyTruncated() {
    // BigDecimal.intValue() is documented to return only the low-order 32 bits when the value is
    // too large, WITHOUT throwing. 3_000_000_000 ms is about 34.7 days; as an int it is
    // -1_294_967_296, which is below any positive floor, so the old comparison would have thrown
    // away the single longest violation in the collection and logged nothing. int milliseconds
    // cap out at roughly 24.8 days, which a stuck camera or a parked forklift reaches easily.
    ReflectionTestUtils.setField(rawEventService, "periodicInputUnit", PeriodicInputUnit.MILLIS);
    BigDecimal beyondIntRange = new BigDecimal("3000000000");

    assertEquals(-1_294_967_296, beyondIntRange.intValue(),
        "guard: this test is only meaningful while intValue() really does wrap");

    rawEventService.listener(rawEvent(EventNameEnum.NO_HELMET, beyondIntRange));

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(0, eventCaptor.getValue().getTimePeriod().compareTo(beyondIntRange));
  }

  /**
   * Closes the loop between this slice and the migration. The migration selects periodic documents
   * whose {@code schemaVersion} is ABSENT and multiplies them by 1000. A listener that writes
   * already-normalised milliseconds without stamping the version would therefore produce documents
   * that a later migration run silently multiplies a second time - and the engine is normally
   * deployed before the migration is switched on, so that window is the normal case, not an edge.
   */
  @Test
  @DisplayName("periodic events are stamped schemaVersion=2, so the migration cannot double-count them")
  void periodicEvent_isStampedWithTheMillisecondsSchemaVersion() {
    rawEventService.listener(rawEvent(EventNameEnum.NO_HELMET, new BigDecimal("4")));

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(Event.SCHEMA_VERSION_MILLIS, eventCaptor.getValue().getSchemaVersion(),
        "a document written in milliseconds must say so, or the migration will convert it again");
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

  // ---------------------------------------------------------------------------------------------
  // The last document shape where "every stored duration is in milliseconds" was not true by
  // construction.
  //
  // The else branch wrote data.getTimePeriod() VERBATIM - un-normalised, and unstamped with a
  // schemaVersion - for every countable type. EventService divides every stored duration by 1000
  // on the way out (toWholeSeconds / toWholeSecondsOrNull, which /event/all-events applies to
  // every row), so a countable event that arrived carrying a raw `5` would have rendered as 0 s
  // in the grid where the design says the cell must read "-", and the PDF would have printed
  // "Time Period: 0 s".
  //
  // The detector cannot produce one - DetectionEvent.__post_init__ rejects a countable event
  // carrying a duration - but the topic is unauthenticated and the listener is the boundary.
  // ---------------------------------------------------------------------------------------------

  @Test
  @DisplayName("countable event carrying a duration: the duration is DISCARDED, the event is kept")
  void countableEventWithADuration_hasTheDurationDiscarded() {
    RawEvent event = rawEvent(EventNameEnum.ARMS_UP, new BigDecimal("5"));

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.ARMS_UP.name(), eventCaptor.getValue().getEventType());
    assertNull(eventCaptor.getValue().getTimePeriod(),
        "a countable event has no duration; storing one asserts a measurement nobody made");
    assertEquals(1, logsAt(Level.WARN).size(),
        "the contract violation is worth one WARNING - it means a producer is misbehaving");
  }

  @Test
  @DisplayName("FALL carrying a duration is still PERSISTED - the duration is dropped, never the event")
  void fallWithADuration_isStillPersisted() {
    // Explicitly not "reject the event": discarding a FALL because a field was populated that
    // should not have been would recreate, by another route, exactly the data loss that the mail
    // isolation above exists to prevent. The bad field is dropped; the safety record survives.
    RawEvent event = rawEvent(EventNameEnum.FALL, new BigDecimal("9999"));

    when(userService.getAllUsers()).thenReturn(List.of());
    when(userResponseDto2UserConverter.convert(List.<UserResponseDto>of())).thenReturn(List.of());

    rawEventService.listener(event);

    verify(eventRepository, times(1)).save(eventCaptor.capture());
    assertEquals(EventNameEnum.FALL.name(), eventCaptor.getValue().getEventType());
    assertNull(eventCaptor.getValue().getTimePeriod());
  }

  @Test
  @DisplayName("unrecognised eventType: DROPPED with one WARNING, exactly as a null type is")
  void unknownEventType_isDropped() {
    // INVERTED. This previously asserted the event WAS saved:
    //
    //     verify(eventRepository, times(1)).save(eventCaptor.capture());
    //     assertEquals("SOMETHING_THE_BACKEND_HAS_NEVER_HEARD_OF",
    //         eventCaptor.getValue().getEventType());
    //
    // and carried the note "A later slice deliberately inverts this to reject-by-default."
    // This is that slice. Nothing validated eventType against EventNameEnum, so anything the
    // detector put on the topic fell through to the else branch and was stored - even with a
    // timePeriod of zero, below the floor that would have rejected a known periodic event.
    //
    // Reject-by-default is the correct rule because storing was never useful: see
    // unknownEventType_isNotStoredWhereNoQueryCanReachIt below.
    RawEvent event = rawEvent("SOMETHING_THE_BACKEND_HAS_NEVER_HEARD_OF", BigDecimal.ZERO);

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
    verifyNoInteractions(mailService, userService, userResponseDto2UserConverter);

    // One WARNING, matching how a null eventType is already handled: the drop is a decision the
    // listener owns, so it is logged once here rather than thrown at the container to retry.
    assertEquals(1, logsAt(Level.WARN).size(), "exactly one WARNING describing the drop");
    assertTrue(logsAt(Level.WARN).get(0).getFormattedMessage()
            .contains("SOMETHING_THE_BACKEND_HAS_NEVER_HEARD_OF"),
        "the WARNING must name the type that was rejected, or it cannot be acted on");
  }

  @Test
  @DisplayName("a detector typo is dropped, not written somewhere no query can ever reach it")
  void unknownEventType_isNotStoredWhereNoQueryCanReachIt() {
    // INVERTED. This previously asserted the typo WAS stored:
    //
    //     verify(eventRepository, times(1)).save(eventCaptor.capture());
    //     assertEquals("TYPO_IN_THE_DETECTOR", eventCaptor.getValue().getEventType());
    //
    // The reason storing was pointless: EventService only ever queries
    // findAllByEventTypeIn([the five known names], ...), so a document with any other eventType
    // could never be read back by any endpoint. It was write-only - it grew the collection and
    // its indexes, appeared in no chart, no grid and no PDF, and could not even be found to be
    // deleted. Dropping it loses nothing that was ever retrievable and leaves a log line, which
    // is strictly more than the silent write left behind.
    rawEventService.listener(rawEvent("TYPO_IN_THE_DETECTOR", null));

    verify(eventRepository, never()).save(any(Event.class));
    assertEquals(1, logsAt(Level.WARN).size());
    assertTrue(logsAt(Level.WARN).get(0).getFormattedMessage().contains("TYPO_IN_THE_DETECTOR"));
  }

  @Test
  @DisplayName("null eventType: dropped silently, nothing persisted, nothing thrown")
  void nullEventType_isDropped() {
    // CHANGED, and the only assertion in this class that was changed. It previously read
    //
    //     assertThrows(NullPointerException.class, () -> rawEventService.listener(event));
    //
    // pinning the fact that a payload which simply omits eventType (RawEvent is
    // @JsonIgnoreProperties(ignoreUnknown = true), so the field arrives null) blew up on the
    // first .equals(...) call. That NPE escaped into the listener container, which re-invoked
    // the listener ten times for the same record before giving up - see
    // RawEventListenerIT.missingEventTypeIsDroppedAndTheNextEventStillArrives, which measured
    // exactly ten invocations against a real broker.
    //
    // Throwing is now the wrong behaviour by contract: an event with no type can never be
    // routed, so the listener drops it itself rather than handing the container an exception to
    // retry. The routing rules for every event type that HAS a type are untouched.
    RawEvent event = rawEvent((String) null, null);

    rawEventService.listener(event);

    verify(eventRepository, never()).save(any(Event.class));
    verifyNoInteractions(mailService, userService, userResponseDto2UserConverter);
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
