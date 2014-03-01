ALTER TABLE confreg_registrationclass ADD COLUMN badgeforegroundcolor varchar(20);
UPDATE confreg_registrationclass SET badgeforegroundcolor='';
ALTER TABLE confreg_registrationclass ALTER COLUMN badgeforegroundcolor SET NOT NULL;
