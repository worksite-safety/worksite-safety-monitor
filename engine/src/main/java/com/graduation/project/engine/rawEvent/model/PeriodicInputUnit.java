package com.graduation.project.engine.rawEvent.model;

import java.math.BigDecimal;

/**
 * The unit in which the detector currently sends {@code timePeriod} on the {@code rawEvents} topic.
 *
 * <h2>Why this exists rather than a single renamed property</h2>
 *
 * <p>The detector and the engine are separate deployments. The detector was rewritten to send
 * {@code timePeriod} in milliseconds; it previously sent {@code int(seconds)} next to a millisecond
 * {@code startTime}. Simply renaming {@code event.fall.threshold.value} to a millisecond threshold
 * and flipping its value from {@code 3} to {@code 3000} would be correct only if both sides
 * deployed at the same instant. They do not, and both orderings fail silently:
 *
 * <ul>
 *   <li>engine first: a 3000 ms threshold compared against a producer still sending seconds means
 *       {@code 3 > 3000} is false for every plausible violation, so <em>nothing</em> is stored and
 *       the dashboard simply goes flat;</li>
 *   <li>detector first (the situation as deployed today): milliseconds compared against {@code 3}
 *       stores nearly everything, including a 33 ms flicker, and the collection fills with noise
 *       that is indistinguishable from real violations.</li>
 * </ul>
 *
 * <p>Making the producer's unit an explicit input decouples the two: the engine is told what it is
 * being sent and converts, so either side may deploy first. {@code SECONDS} is the default because
 * it describes the producer that is in the field <em>before</em> the rewrite ships; flipping the
 * property to {@code MILLIS} is the one-line, no-rebuild step that accompanies the detector
 * release.
 *
 * <p>Storage is always milliseconds regardless of this setting - see
 * {@code RawEventService.listener}. The unit lives at the boundary and nowhere else.
 */
public enum PeriodicInputUnit {

  /** The pre-rewrite detector: {@code timePeriod} arrives as whole seconds. */
  SECONDS {
    @Override
    public BigDecimal toMillis(BigDecimal value) {
      return value.multiply(THOUSAND);
    }
  },

  /** The rewritten detector: {@code timePeriod} already arrives as milliseconds. */
  MILLIS {
    @Override
    public BigDecimal toMillis(BigDecimal value) {
      return value;
    }
  };

  private static final BigDecimal THOUSAND = BigDecimal.valueOf(1000);

  /**
   * Normalises an incoming {@code timePeriod} to milliseconds.
   *
   * <p>Deliberately {@link BigDecimal} in and out: the wire value is bound to a {@code BigDecimal}
   * and the stored value is a {@code BigDecimal}, so converting through {@code double} anywhere in
   * between would introduce representation error into a number that is currently exact.
   *
   * @param value the value exactly as it arrived on the topic, never {@code null}
   * @return the same duration expressed in milliseconds
   */
  public abstract BigDecimal toMillis(BigDecimal value);
}
