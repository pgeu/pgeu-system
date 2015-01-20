ALTER TABLE confsponsor_sponsorshiplevel ADD COLUMN available boolean NOT NULL DEFAULT 't';
ALTER TABLE confsponsor_sponsorshiplevel ALTER COLUMN available DROP DEFAULT;
