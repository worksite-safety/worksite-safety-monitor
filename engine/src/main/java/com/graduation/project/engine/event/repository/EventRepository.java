package com.graduation.project.engine.event.repository;

import com.graduation.project.engine.event.model.Event;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

import java.util.List;

public interface EventRepository extends MongoRepository<Event, String> {

  /**
   * Every event of one of {@code eventType}, whose {@code startTime} falls inside the CLOSED
   * interval {@code [startTime, endTime]}, oldest first.
   *
   * <h2>Why this is a {@code @Query} and not a derived query</h2>
   *
   * <p>This is the single funnel behind every date-range feature in the application - the
   * countable chart, the pie chart, the periodic chart, the events grid and the emailed PDF all
   * reach the database through {@code EventService.getAllEventsByEventTypes}. Whatever this method
   * does, all five inherit.
   *
   * <p>It used to be a derived query, and the derivation was wrong. Spring Data MongoDB's
   * {@code MongoQueryCreator} maps the {@code BETWEEN} keyword to {@code $gt}/{@code $lt} -
   * EXCLUSIVE at both ends - unlike JPA, where {@code Between} is inclusive. An event whose
   * {@code startTime} equalled the requested start or end to the millisecond was therefore
   * dropped from every one of those five features. Nothing failed; the numbers were quietly a
   * little too small. The UI sends day boundaries, so what it lost was events at exactly midnight.
   * Measured against a real server in {@code EventRepositoryIT}, not inferred.
   *
   * <p>Writing the filter out by hand puts the operators in the source, where they can be read and
   * where {@code EventRepositoryIT#rangeQueryMatchesGteLteNotGtLt} can compare them against the
   * raw queries. It also decouples the semantics from the framework: a future Spring Data version
   * that changed the {@code BETWEEN} mapping - in either direction - would silently change the
   * meaning of a derived method, and this one it cannot touch.
   *
   * <h2>Why the method KEEPS its name</h2>
   *
   * <p>{@code Between} in ordinary English, and in JPA, denotes the closed interval, which is now
   * exactly what this returns; it was Spring Data's derivation that disagreed with the name, not
   * the name that was wrong. Keeping it also keeps the change to the defect: the name is the
   * repository's published API and {@code EventService} plus five characterization assertions in
   * {@code EventServiceTest} refer to it. With {@code @Query} present the name is never parsed by
   * Spring Data at all, so it is now a plain identifier and cannot re-acquire {@code $gt}/{@code $lt}
   * by accident.
   *
   * <p>{@code sort} is an attribute here rather than the {@code OrderByStartTimeAsc} suffix for
   * the same reason - the suffix is part of the derivation, which no longer runs. Pinned by
   * {@code EventRepositoryIT#resultsAreSortedByStartTimeAscending}.
   *
   * @param eventType the event types to include, matched with {@code $in}
   * @param startTime lower bound, INCLUSIVE, epoch milliseconds
   * @param endTime   upper bound, INCLUSIVE, epoch milliseconds
   */
  @Query(value = "{ 'eventType': { '$in': ?0 }, 'startTime': { '$gte': ?1, '$lte': ?2 } }",
      sort = "{ 'startTime': 1 }")
  List<Event> findAllByEventTypeInAndStartTimeBetweenOrderByStartTimeAsc(List<String> eventType,
      Long startTime, Long endTime);
}
