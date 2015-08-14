ALTER TABLE confreg_conference ADD COLUMN attendees_before_waitlist int NOT NULL DEFAULT 0;
ALTER TABLE confreg_conference ALTER COLUMN attendees_before_waitlist DROP DEFAULT;
