ALTER TABLE confreg_conference ADD COLUMN sendwelcomemail boolean NOT NULL DEFAULT 'f';
ALTER TABLE confreg_conference ALTER COLUMN sendwelcomemail DROP DEFAULT;
ALTER TABLE confreg_conference ADD COLUMN welcomemail text NOT NULL DEFAULT '';
ALTER TABLE confreg_conference ALTER COLUMN welcomemail DROP DEFAULT;
