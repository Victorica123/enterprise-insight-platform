package com.example.videoplatform.workflow;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TaskStageLogRepository extends JpaRepository<TaskStageLog, Long> {
    List<TaskStageLog> findByTaskIdAndIdGreaterThanOrderByIdAsc(String taskId, long after, Pageable page);
    List<TaskStageLog> findByStartedAtBeforeOrderByIdAsc(Instant cutoff, Pageable page);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update TaskStageLog s set s.status = :status, s.finishedAt = :now, s.durationMs = :duration, "
            + "s.errorCode = :error where s.id = :id and s.status = 'RUNNING'")
    int finishRunning(@Param("id") long id, @Param("status") String status, @Param("now") Instant now,
                      @Param("duration") long duration, @Param("error") String error);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update TaskStageLog s set s.status = 'ABANDONED', s.finishedAt = :now, s.errorCode = 'LEASE_RECOVERED' "
            + "where s.taskId = :taskId and s.status = 'RUNNING' and s.stage <> 'DELIVERY'")
    int abandonProcessing(@Param("taskId") String taskId, @Param("now") Instant now);
}
