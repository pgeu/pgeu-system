CREATE OR REPLACE FUNCTION speaker_deleted()
RETURNS trigger AS $$
BEGIN
   INSERT INTO confreg_deleteditems (itemid, type, deltime) VALUES (OLD.id, 'spk', CURRENT_TIMESTAMP);
   RETURN NULL;
END;
$$ LANGUAGE 'plpgsql';

DROP TRIGGER IF EXISTS trg_speaker_deleted ON confreg_speaker;
CREATE TRIGGER trg_speaker_deleted
AFTER DELETE ON confreg_speaker
FOR EACH ROW EXECUTE PROCEDURE speaker_deleted();

