ALTER TABLE confreg_shirtsize ADD COLUMN sortkey integer NOT NULL DEFAULT 100;
ALTER TABLE confreg_shirtsize ALTER COLUMN sortkey DROP DEFAULT;
