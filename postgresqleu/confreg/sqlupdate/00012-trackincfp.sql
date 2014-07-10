ALTER TABLE confreg_track ADD COLUMN incfp boolean NOT NULL DEFAULT 'f';
ALTER TABLE confreg_track ALTER COLUMN incfp DROP DEFAULT;
