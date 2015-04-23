ALTER TABLE confreg_conference ADD COLUMN twitter_sponsorlist varchar(32) NOT NULL DEFAULT '';
ALTER TABLE confreg_conference ALTER COLUMN twitter_sponsorlist DROP DEFAULT;
