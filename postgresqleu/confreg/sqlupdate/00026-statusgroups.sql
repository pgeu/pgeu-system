ALTER TABLE confreg_status_strings ADD COLUMN statusgroup text NULL;
UPDATE confreg_status_strings SET statusgroup='Approved+Pending' WHERE id IN (1, 3);
