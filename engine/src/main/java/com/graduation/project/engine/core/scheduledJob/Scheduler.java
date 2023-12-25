package com.graduation.project.engine.core.scheduledJob;


import com.graduation.project.engine.models.DefaultStats;
import com.graduation.project.engine.models.Event;
import com.graduation.project.engine.models.RawEvent;
import com.graduation.project.engine.repository.EventRepository;
import com.graduation.project.engine.repository.RawEventRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Objects;

@Component
@RequiredArgsConstructor
public class Scheduler {

    Logger logger = LoggerFactory.getLogger(Scheduler.class);
    private final RawEventRepository rawEventRepository;
    private final EventRepository eventRepository;

    @Scheduled(fixedDelay = 1000000000) // Run every day at 00:02 cron = "2 0 * * * *"
    public void recordResults() {

        logger.info("Scheduling is running...");

        LocalDateTime currentDateTime = LocalDateTime.now();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MMM/yyyy HH:mm", Locale.ENGLISH);
        String dateTimeRecord = currentDateTime.format(formatter);
        long numberOfEvents = rawEventRepository.count();
        double confidencePercentageSum = 0;
        int totalDetectedFall = 0;


        for (RawEvent rawEvent : rawEventRepository.findAll()) {

            confidencePercentageSum += Double.parseDouble(rawEvent.getConfidencePercentage()) * 100;
            if (rawEvent.getEventPrediction().equals("fall")) {
                totalDetectedFall++;
            }

        }
        double averageConfidenceRate = confidencePercentageSum / numberOfEvents;


        DefaultStats defaultStats = DefaultStats.builder()
                .totalDetectedFall(totalDetectedFall)
                .averageConfidenceRate(averageConfidenceRate)
                .build();

        logger.info("Scheduling is done.");
        eventRepository.save(Event.builder()
                .build());
    }
}
