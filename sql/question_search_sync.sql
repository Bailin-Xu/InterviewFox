-- Run once against the InterviewFox database before enabling Elasticsearch search.
CREATE TABLE IF NOT EXISTS question_search_sync_state (
    id TINYINT NOT NULL PRIMARY KEY,
    index_uuid VARCHAR(64) NULL,
    backfill_cursor BIGINT NOT NULL DEFAULT 0,
    backfill_complete BOOLEAN NOT NULL DEFAULT FALSE
) ENGINE = InnoDB;

INSERT IGNORE INTO question_search_sync_state (id) VALUES (1);

CREATE TABLE IF NOT EXISTS question_search_outbox (
    event_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    question_id BIGINT NOT NULL
) ENGINE = InnoDB;

CREATE TRIGGER question_search_after_insert AFTER INSERT ON question
FOR EACH ROW INSERT INTO question_search_outbox (question_id) VALUES (NEW.id);

CREATE TRIGGER question_search_after_update AFTER UPDATE ON question
FOR EACH ROW INSERT INTO question_search_outbox (question_id)
SELECT NEW.id UNION SELECT OLD.id;

CREATE TRIGGER question_search_after_delete AFTER DELETE ON question
FOR EACH ROW INSERT INTO question_search_outbox (question_id) VALUES (OLD.id);
