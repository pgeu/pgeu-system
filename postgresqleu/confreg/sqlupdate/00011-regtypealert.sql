ALTER TABLE confreg_registrationtype ADD COLUMN alertmessage text NOT NULL DEFAULT '';
ALTER TABLE confreg_registrationtype ALTER COLUMN alertmessage DROP DEFAULT;
