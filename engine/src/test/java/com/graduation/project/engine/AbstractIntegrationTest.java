package com.graduation.project.engine;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.lifecycle.Startables;
import org.testcontainers.utility.DockerImageName;

/**
 * Base class for every {@code *IT} in this module. Requires a running Docker daemon.
 *
 * <h2>Singleton containers, not {@code @Container}</h2>
 *
 * <p>The containers are {@code static} and started once from a static initialiser - the
 * "singleton container" pattern - rather than being managed per class by
 * {@code @Testcontainers}/{@code @Container}. Combined with Failsafe's
 * {@code forkCount=1}/{@code reuseForks=true} (see pom.xml) every IT class in the suite runs in
 * the same JVM, so the statics really are shared and container startup is paid exactly once for
 * the whole integration run instead of once per class.
 *
 * <p>Nothing stops the containers. That is correct: the JVM exits at the end of the Failsafe
 * fork and Testcontainers' Ryuk sidecar reaps them. An explicit {@code stop()} would only be a
 * chance to leave them running when a test crashes.
 *
 * <p>{@code withReuse(true)} is deliberately NOT used. It is pleasant locally but leaks state
 * between runs and is the wrong default for CI, where every build must start from an empty
 * database and an empty broker.
 *
 * <h2>Why Testcontainers and not the alternatives</h2>
 *
 * <ul>
 *   <li>flapdoodle would download a native {@code mongod} from a remote mirror at test time.</li>
 *   <li>{@code @EmbeddedKafka} works today, but {@code spring-kafka-test:3.0.10} boots a
 *       ZooKeeper broker while 3.1+ defaults to KRaft - so it is the single component most
 *       likely to need rework during the Boot 3.0.4 -> 3.5.x upgrade, i.e. precisely when
 *       these tests have to be a trustworthy oracle. A container is decoupled from the
 *       spring-kafka version entirely.</li>
 * </ul>
 *
 * <p>The Kafka image is {@code apache/kafka} (KRaft) driven through
 * {@code org.testcontainers.kafka.KafkaContainer}, not the deprecated
 * {@code org.testcontainers.containers.KafkaContainer} which shells out to
 * {@code confluentinc/cp-kafka}.
 *
 * <h2>Configuration</h2>
 *
 * <p>{@code src/test/resources/application.yml} shadows the production config and points Mongo
 * and Kafka at unreachable placeholders. {@link DynamicPropertySource} has higher precedence
 * than any property source loaded from a file, so the two entries below are what the context
 * actually sees. Everything else - the {@code test} profile's mail settings, image path and
 * {@code event.fall.threshold.value} - is untouched.
 */
@SpringBootTest
@ActiveProfiles("test")
public abstract class AbstractIntegrationTest {

  /**
   * Both tags are pinned rather than floating: an IT suite whose fixtures change under it when
   * Docker Hub publishes a new {@code latest} is not an oracle.
   */
  private static final DockerImageName MONGO_IMAGE = DockerImageName.parse("mongo:8.0.17");

  private static final DockerImageName KAFKA_IMAGE = DockerImageName.parse("apache/kafka:4.1.1");

  private static final String DATABASE_NAME = "engine-it";

  protected static final MongoDBContainer MONGO_DB = new MongoDBContainer(MONGO_IMAGE);

  protected static final KafkaContainer KAFKA = new KafkaContainer(KAFKA_IMAGE);

  /**
   * Docker Engine API version handshake.
   *
   * <p>Testcontainers 1.21.3 shades docker-java 3.4.2, which defaults to Engine API {@code v1.32}.
   * Docker Engine 29.x advertises {@code API version 1.55 (minimum version 1.40)} and answers
   * {@code GET /v1.32/info} with {@code 400 Bad Request}. Testcontainers reports that as the
   * thoroughly misleading "Could not find a valid Docker environment", because a failed probe is
   * indistinguishable from an absent daemon.
   *
   * <p>{@code api.version} is docker-java's own system property, read by
   * {@code DefaultDockerClientConfig.createDefaultConfigBuilder()}. It is set here rather than in
   * the Failsafe configuration so that running an IT straight from the IDE works too. An external
   * {@code -Dapi.version=...} still wins.
   */
  private static final String DOCKER_API_VERSION = "1.44";

  static {
    System.setProperty("api.version", System.getProperty("api.version", DOCKER_API_VERSION));

    long startedAt = System.currentTimeMillis();
    // deepStart brings both up concurrently; sequential start() calls would add the two
    // startup times together for no reason.
    Startables.deepStart(MONGO_DB, KAFKA).join();
    System.out.printf(
        "[AbstractIntegrationTest] containers up in %d ms (mongo=%s, kafka=%s)%n",
        System.currentTimeMillis() - startedAt,
        MONGO_DB.getReplicaSetUrl(DATABASE_NAME),
        KAFKA.getBootstrapServers());
  }

  @DynamicPropertySource
  static void containerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri", () -> MONGO_DB.getReplicaSetUrl(DATABASE_NAME));
    registry.add("spring.kafka.bootstrap-servers", KAFKA::getBootstrapServers);
  }
}
