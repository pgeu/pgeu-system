ALTER TABLE confreg_conference ADD COLUMN twittersync_active boolean default 'f';
ALTER TABLE confreg_conference ALTER COLUMN twittersync_active DROP DEFAULT;
