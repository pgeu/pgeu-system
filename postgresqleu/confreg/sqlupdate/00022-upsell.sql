ALTER TABLE confreg_registrationtype ADD COLUMN upsell_target boolean NOT NULL DEFAULT 'f';
ALTER TABLE confreg_registrationtype ALTER COLUMN upsell_target DROP DEFAULT;

ALTER TABLE confreg_conferenceadditionaloption ADD COLUMN upsellable boolean NOT NULL DEFAULT 'f';
ALTER TABLE confreg_conferenceadditionaloption ALTER COLUMN upsellable DROP DEFAULT;

