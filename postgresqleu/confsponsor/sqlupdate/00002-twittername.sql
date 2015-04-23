ALTER TABLE confsponsor_sponsor ADD COLUMN twittername varchar(100) NOT NULL DEFAULT '';
ALTER TABLE confsponsor_sponsor ALTER COLUMN twittername DROP DEFAULT;
