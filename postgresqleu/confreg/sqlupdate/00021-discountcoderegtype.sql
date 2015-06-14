CREATE TABLE "confreg_discountcode_requiresregtype" (
	"id" serial NOT NULL PRIMARY KEY,
	"discountcode_id" integer NOT NULL,
	"registrationtype_id" integer NOT NULL REFERENCES "confreg_registrationtype" ("id") DEFERRABLE INITIALLY DEFERRED,
	 UNIQUE ("discountcode_id", "registrationtype_id")
);

ALTER TABLE "confreg_discountcode_requiresregtype" ADD CONSTRAINT "discountcode_id_refs_id_ff209aae" FOREIGN KEY ("discountcode_id") REFERENCES "confreg_discountcode" ("id") DEFERRABLE INITIALLY DEFERRED;


