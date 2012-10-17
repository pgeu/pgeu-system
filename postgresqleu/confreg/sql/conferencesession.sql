CREATE OR REPLACE FUNCTION conferencesession_deleted()
RETURNS trigger AS $$
BEGIN
   INSERT INTO confreg_deleteditems (itemid, type, deltime) VALUES (OLD.id, 'sess', CURRENT_TIMESTAMP);
   RETURN NULL;
END;
$$ LANGUAGE 'plpgsql';

DROP TRIGGER IF EXISTS trg_conferencesession_deleted ON confreg_conferencesession;
CREATE TRIGGER trg_conferencesession_deleted
AFTER DELETE ON confreg_conferencesession
FOR EACH ROW EXECUTE PROCEDURE conferencesession_deleted();

