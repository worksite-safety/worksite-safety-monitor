package com.graduation.project.engine;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.apache.kafka.clients.admin.TopicDescription;
import org.bson.Document;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.kafka.core.KafkaAdmin;

/**
 * Smoke test: the full application context must start against real infrastructure.
 *
 * <p>This replaces the old {@code EngineApplicationTests}, which had to
 * {@code @MockBean KafkaAdmin} so that the {@code NewTopic} bean declared by
 * {@code KafkaTopicConfig} was not pushed to a broker that did not exist. That mock was a
 * workaround for the absence of a broker, and it hollowed the test out: a context that starts
 * only because its Kafka client is a Mockito stub proves very little. Here the broker is real,
 * KafkaAdmin runs for real, and the topic it creates is asserted.
 */
class EngineApplicationIT extends AbstractIntegrationTest {

  @Autowired
  private MongoTemplate mongoTemplate;

  @Autowired
  private KafkaAdmin kafkaAdmin;

  @Value("${kafka.raw-event.topic}")
  private String rawEventTopic;

  @Test
  @DisplayName("context starts and MongoDB is actually reachable")
  void contextLoads() {
    Document ping = mongoTemplate.executeCommand(new Document("ping", 1));

    assertThat(ping.get("ok")).isEqualTo(1.0);
    assertThat(mongoTemplate.getDb().getName()).isEqualTo("engine-it");
  }

  @Test
  @DisplayName("KafkaAdmin created the NewTopic bean on a real broker - no @MockBean needed")
  void kafkaTopicIsCreatedOnTheBroker() {
    Map<String, TopicDescription> topics = kafkaAdmin.describeTopics(rawEventTopic);

    assertThat(topics).containsKey(rawEventTopic);
    assertThat(topics.get(rawEventTopic).partitions()).isNotEmpty();
  }
}
