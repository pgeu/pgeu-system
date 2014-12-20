ALTER TABLE confreg_conference ADD COLUMN callforsponsorsopen boolean NOT NULL DEFAULT 'f';
ALTER TABLE confreg_conference ALTER COLUMN callforsponsorsopen DROP DEFAULT;
ALTER TABLE confreg_conference ADD COLUMN sponsoraddr varchar(75) NOT NULL DEFAULT '';
ALTER TABLE confreg_conference ALTER COLUMN sponsoraddr DROP DEFAULT;
UPDATE confreg_conference SET sponsoraddr=contactaddr;
