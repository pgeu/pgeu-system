ALTER TABLE confsponsor_sponsorshiplevel ADD COLUMN canbuyvoucher boolean NOT NULL DEFAULT 't';
ALTER TABLE confsponsor_sponsorshiplevel ALTER COLUMN canbuyvoucher DROP DEFAULT;

ALTER TABLE confsponsor_sponsorshiplevel ADD COLUMN canbuydiscountcode boolean NOT NULL DEFAULT 't';
ALTER TABLE confsponsor_sponsorshiplevel ALTER COLUMN canbuydiscountcode DROP DEFAULT;

ALTER TABLE confreg_prepaidbatch ADD COLUMN sponsor_id int REFERENCES confsponsor_sponsor(id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "confreg_prepaidbatch_sponsor_id" ON "confreg_prepaidbatch" ("sponsor_id");

ALTER TABLE confreg_discountcode ADD COLUMN sponsor_id int REFERENCES confsponsor_sponsor(id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "confreg_discountcode_sponsor_id" ON "confreg_discountcode" ("sponsor_id");
ALTER TABLE confreg_discountcode ADD COLUMN sponsor_rep_id int REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX "confreg_discountcode_sponsor_rep_id" ON "confreg_discountcode" ("sponsor_rep_id");
ALTER TABLE confreg_discountcode ADD COLUMN is_invoiced boolean NOT NULL DEFAULT 'f';
ALTER TABLE confreg_discountcode ALTER COLUMN is_invoiced DROP DEFAULT;
