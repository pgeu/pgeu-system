ALTER TABLE confreg_conferencesession ADD COLUMN lastnotifiedstatus int;
UPDATE confreg_conferencesession SET lastnotifiedstatus=status;
