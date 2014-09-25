CREATE TABLE "confreg_discountcode_requiresoption" (
    "id" serial NOT NULL PRIMARY KEY,
    "discountcode_id" integer NOT NULL,
    "conferenceadditionaloption_id" integer NOT NULL REFERENCES "confreg_conferenceadditionaloption" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("discountcode_id", "conferenceadditionaloption_id")
)
;
ALTER TABLE "confreg_discountcode_requiresoption" ADD CONSTRAINT "discountcode_id_refs_id_39bc2fc" FOREIGN KEY ("discountcode_id") REFERENCES "confreg_discountcode" ("id") DEFERRABLE INITIALLY DEFERRED;
