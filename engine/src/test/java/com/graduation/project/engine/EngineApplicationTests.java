package com.graduation.project.engine;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.test.context.ActiveProfiles;

/**
 * Smoke test: the full application context must start.
 *
 * <p>KafkaAdmin is mocked out so the {@code NewTopic} bean declared by
 * {@code KafkaTopicConfig} is not pushed to a real broker during startup.
 */
@SpringBootTest
@ActiveProfiles("test")
class EngineApplicationTests {

  @MockBean
  private KafkaAdmin kafkaAdmin;

  @Test
  void contextLoads() {
  }

}
