package com.berlin.interviewfox.service.search

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper
import com.berlin.interviewfox.mapper.QuestionMapper
import com.berlin.interviewfox.model.entity.Question
import org.slf4j.LoggerFactory
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Component
import org.springframework.transaction.annotation.Isolation
import org.springframework.transaction.annotation.Transactional

@Component
@ConditionalOnProperty(prefix = "interviewfox.search.elasticsearch", name = ["enabled"], havingValue = "true")
class QuestionIndexSync(
    private val jdbc: JdbcTemplate,
    private val questionMapper: QuestionMapper,
    private val index: QuestionSearchIndex
) {
    @Scheduled(fixedDelayString = "\${interviewfox.search.elasticsearch.sync-delay-ms:1000}")
    @Transactional(isolation = Isolation.READ_COMMITTED, rollbackFor = [Exception::class])
    fun sync() {
        // Serializes sync workers across application instances without locking question writes.
        val state = checkNotNull(jdbc.queryForObject(
            """
                SELECT index_uuid, backfill_cursor, backfill_complete
                FROM question_search_sync_state WHERE id = 1 FOR UPDATE
            """.trimIndent(),
            RowMapper { row, _ ->
                SyncState(row.getString("index_uuid"), row.getLong("backfill_cursor"), row.getBoolean("backfill_complete"))
            }
        ))
        val uuid = index.ensureIndex()
        if (state.indexUuid != uuid) {
            index.ready = false
            jdbc.update(
                """
                    UPDATE question_search_sync_state
                    SET index_uuid = ?, backfill_cursor = 0, backfill_complete = FALSE WHERE id = 1
                """.trimIndent(), uuid
            )
            LOG.info("Starting full question sync for index {}", uuid)
            backfill(0)
        } else if (!state.backfillComplete) {
            backfill(state.cursor)
        } else {
            syncChanges()
        }
    }

    private fun backfill(cursor: Long) {
        val questions = questionMapper.selectList(
            QueryWrapper<Question>().gt("id", cursor).orderByAsc("id").last("LIMIT $BATCH_SIZE")
        )
        index.write(questions)
        jdbc.update(
            "UPDATE question_search_sync_state SET backfill_cursor = ?, backfill_complete = ? WHERE id = 1",
            questions.lastOrNull()?.id ?: cursor, questions.size < BATCH_SIZE
        )
    }

    private fun syncChanges() {
        val changes = jdbc.query(
            "SELECT event_id, question_id FROM question_search_outbox ORDER BY event_id LIMIT ?",
            RowMapper { row, _ -> Change(row.getLong("event_id"), row.getLong("question_id")) }, BATCH_SIZE
        )
        if (changes.isEmpty()) {
            if (!index.ready) {
                index.refresh()
                index.ready = true
                LOG.info("Question Elasticsearch index is ready")
            }
            return
        }

        // Read the latest committed row. A missing or logically deleted row means delete in ES.
        val questionIds = changes.map { it.questionId }.toSet()
        val questions = questionMapper.selectBatchIds(questionIds)
        val deletedIds = questionIds - questions.map { it.id }.toSet()
        index.write(questions, deletedIds)

        // Acknowledge specific events only. Auto-increment IDs can commit out of order.
        val placeholders = changes.joinToString(",") { "?" }
        jdbc.update(
            "DELETE FROM question_search_outbox WHERE event_id IN ($placeholders)",
            *changes.map { it.eventId }.toTypedArray()
        )
    }

    private data class SyncState(val indexUuid: String?, val cursor: Long, val backfillComplete: Boolean)
    private data class Change(val eventId: Long, val questionId: Long)

    private companion object {
        const val BATCH_SIZE = 500
        val LOG = LoggerFactory.getLogger(QuestionIndexSync::class.java)
    }
}
