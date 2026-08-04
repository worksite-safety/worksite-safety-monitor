package com.graduation.project.engine.core.messageBrokerConfig;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.graduation.project.engine.rawEvent.model.RawEvent;
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.NestedExceptionUtils;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Consumer-side Kafka wiring for the single {@code rawEvents} listener.
 *
 * <h2>Contract: a malformed event is dropped, never retried</h2>
 *
 * <p>The producer is an unauthenticated Python process on a topic with no schema registry, so
 * "bytes that are not a {@code RawEvent}" is a normal operating condition, not an incident. The
 * only acceptable response is to log the offset once and move on. Anything else - a retry loop,
 * or worse, no handling at all - converts one bad message into an outage of the entire pipeline,
 * because the topic has one partition and one consumer group.
 *
 * <h2>Why {@link ErrorHandlingDeserializer} rather than an error handler alone</h2>
 *
 * <p>A deserialisation failure does not happen while a record is being delivered; it happens
 * inside {@code Consumer.poll()}, in {@code Fetcher.parseRecord}. No {@code ConsumerRecord} is
 * ever constructed, so a {@code CommonErrorHandler} has nothing to skip and the consumer's
 * position never advances. The next poll re-reads the same bytes and fails identically, forever.
 * spring-kafka says so itself, by throwing
 * {@code IllegalStateException: This error handler cannot process 'SerializationException's
 * directly; please consider configuring an 'ErrorHandlingDeserializer'}.
 *
 * <p>{@code ErrorHandlingDeserializer} moves the failure out of {@code poll()}: it returns a null
 * value and stores the exception in a header, the container detects that header before invoking
 * the listener, and the failure becomes an ordinary record-level error that the error handler
 * below can recover from and seek past.
 *
 * <h2>Deserialisers are passed as instances, deliberately</h2>
 *
 * <p>{@link DefaultKafkaConsumerFactory} is given constructed deserialisers rather than classes.
 * When {@code KafkaConsumer} receives an instance it uses it as-is and never calls
 * {@code configure()} on it, which means {@code KEY_DESERIALIZER_CLASS_CONFIG},
 * {@code VALUE_DESERIALIZER_CLASS_CONFIG} and every {@code spring.json.*} property are ignored.
 * The previous version of this class set two of those keys anyway; they were dead weight and are
 * gone. Everything that has to be configured on a deserialiser is therefore configured on the
 * object - see {@code useHeadersIfPresent} below.
 *
 * <h2>Known limitation: {@code spring.kafka.*} properties do not reach this factory</h2>
 *
 * <p>{@link #kafkaListenerContainerFactory()} takes the bean name Spring Boot's own
 * auto-configured factory would have used, so Boot backs off, and this class never applies
 * {@code KafkaProperties} or {@code ConcurrentKafkaListenerContainerFactoryConfigurer}. Every
 * {@code spring.kafka.consumer.*} and {@code spring.kafka.listener.*} entry in any
 * {@code application.yml} is consequently inert - including {@code listener.auto-startup}, which
 * does not stop the container from starting. Only {@code spring.kafka.bootstrap-servers} has any
 * effect, and only because it is read by hand above.
 *
 * <p>Left as-is on purpose. Wiring the configurer in would change the meaning of every
 * {@code spring.kafka.*} property in every environment simultaneously, would let
 * {@code KafkaProperties}' own deserialiser defaults fight the instances constructed here, and is
 * a behavioural change with a far wider blast radius than the poison-pill fix it would be
 * smuggled in beside. It needs its own change, with its own tests.
 */
@Configuration
public class KafkaConsumerConfig {

  private static final Logger LOGGER = LoggerFactory.getLogger(KafkaConsumerConfig.class);

  /**
   * Recovery for a record the pipeline cannot use: exactly one line, then the container seeks
   * past it. The offset is in the message because it is the only way to find the payload again
   * with {@code kafka-console-consumer --partition --offset}; the payload itself is not logged,
   * since it is unvalidated input of unbounded size.
   */
  private static final ConsumerRecordRecoverer DROP_MALFORMED_RECORD = (record, exception) -> {
    // The exception handed to a recoverer is a ListenerExecutionFailedException whose own
    // message is the useless constant "Listener failed"; the reason the record was rejected is
    // always further down the chain.
    Throwable cause = NestedExceptionUtils.getMostSpecificCause(exception);
    LOGGER.warn("Dropping malformed record from {}-{} at offset {}: {}: {}",
        record.topic(), record.partition(), record.offset(),
        cause.getClass().getSimpleName(), cause.getMessage());
  };

  @Value("${spring.kafka.bootstrap-servers}")
  private String bootstrapServers;

  @Bean
  public ConsumerFactory<String, RawEvent> consumerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    // Unset, this defaults to "latest": a consumer group that has never committed silently
    // discards everything already on the topic. That makes the first deployment against an
    // existing topic, any group-id rename and any offset reset lose data without a log line.
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    // useHeadersIfPresent = false. The Python producer sends no __TypeId__ header, so today the
    // deserialiser only reaches the configured target type by falling back to it. That fallback
    // is fragile - any producer that does send a type header would override RawEvent - and the
    // equivalent USE_TYPE_INFO_HEADERS property would be ignored on a constructed instance, so
    // it is pinned on the object instead.
    JsonDeserializer<RawEvent> jsonDeserializer =
        new JsonDeserializer<>(RawEvent.class, new ObjectMapper(), false);

    return new DefaultKafkaConsumerFactory<>(props, new StringDeserializer(),
        new ErrorHandlingDeserializer<>(jsonDeserializer));
  }

  @Bean
  public ConcurrentKafkaListenerContainerFactory<String, RawEvent> kafkaListenerContainerFactory() {
    ConcurrentKafkaListenerContainerFactory<String, RawEvent> factory =
        new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory());
    // FixedBackOff(0, 0) = one attempt, no retries. spring-kafka's default is
    // FixedBackOff(0L, 9L), i.e. the listener is re-invoked ten times for the same record with
    // no pause between attempts - ten rounds of whatever side effects it has already performed,
    // which for a FALL event means ten emails to every user in the database. Nothing about a
    // structurally invalid event becomes valid on the second attempt, so there is nothing to
    // retry.
    factory.setCommonErrorHandler(
        new DefaultErrorHandler(DROP_MALFORMED_RECORD, new FixedBackOff(0L, 0L)));
    return factory;
  }
}
