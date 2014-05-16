ALTER TABLE confreg_conference ADD COLUMN templateoverridedir varchar(128) NOT NULL DEFAULT '';
ALTER TABLE confreg_conference ALTER COLUMN templateoverridedir DROP DEFAULT;
