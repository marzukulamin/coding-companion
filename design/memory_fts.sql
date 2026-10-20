-- Optional migration after an FTS5 feature probe. Core works without it.
-- Coordinator wraps this migration and its ledger row in one transaction.
CREATE VIRTUAL TABLE lesson_search USING fts5(
    lesson_id UNINDEXED,
    summary,
    tags,
    tokenize = 'unicode61'
);

CREATE TRIGGER lesson_search_insert AFTER INSERT ON lessons
WHEN NEW.status = 'verified'
BEGIN
    INSERT INTO lesson_search(lesson_id, summary, tags)
    VALUES (NEW.lesson_id, NEW.summary, NEW.tags);
END;

CREATE TRIGGER lesson_search_update AFTER UPDATE ON lessons
BEGIN
    DELETE FROM lesson_search WHERE lesson_id = OLD.lesson_id;
    INSERT INTO lesson_search(lesson_id, summary, tags)
    SELECT NEW.lesson_id, NEW.summary, NEW.tags WHERE NEW.status = 'verified';
END;

CREATE TRIGGER lesson_search_delete AFTER DELETE ON lessons
BEGIN
    DELETE FROM lesson_search WHERE lesson_id = OLD.lesson_id;
END;

INSERT INTO lesson_search(lesson_id, summary, tags)
SELECT lesson_id, summary, tags FROM lessons WHERE status = 'verified';
-- Search must JOIN lessons and apply scope/expiry/privacy filters.
-- Expiry timestamps do not themselves fire SQL triggers.
