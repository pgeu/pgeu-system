ALTER TABLE confreg_conferenceadditionaloption ADD COLUMN public boolean NOT NULL DEFAULT 't';
ALTER TABLE confreg_conferenceadditionaloption ALTER COLUMN public DROP DEFAULT;
