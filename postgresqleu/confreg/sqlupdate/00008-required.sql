CREATE TABLE "confreg_registrationtype_requires_option" (
    "id" serial NOT NULL PRIMARY KEY,
    "registrationtype_id" integer NOT NULL,
    "conferenceadditionaloption_id" integer NOT NULL,
    UNIQUE ("registrationtype_id", "conferenceadditionaloption_id")
);
ALTER TABLE "confreg_registrationtype_requires_option" ADD CONSTRAINT "registrationtype_id_refs_id_8aaa2552" FOREIGN KEY ("registrationtype_id") REFERENCES "confreg_registrationtype" ("id") DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE "confreg_conferenceadditionaloption_requires_regtype" (
    "id" serial NOT NULL PRIMARY KEY,
    "conferenceadditionaloption_id" integer NOT NULL,
    "registrationtype_id" integer NOT NULL REFERENCES "confreg_registrationtype" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("conferenceadditionaloption_id", "registrationtype_id")
)
;
ALTER TABLE "confreg_registrationtype_requires_option" ADD CONSTRAINT "conferenceadditionaloption_id_refs_id_edb5b651" FOREIGN KEY ("conferenceadditionaloption_id") REFERENCES "confreg_conferenceadditionaloption" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "confreg_conferenceadditionaloption_requires_regtype" ADD CONSTRAINT "conferenceadditionaloption_id_refs_id_837ecbee" FOREIGN KEY ("conferenceadditionaloption_id") REFERENCES "confreg_conferenceadditionaloption" ("id") DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE "confreg_conferenceadditionaloption_mutually_exclusive" (
    "id" serial NOT NULL PRIMARY KEY,
    "from_conferenceadditionaloption_id" integer NOT NULL,
    "to_conferenceadditionaloption_id" integer NOT NULL,
    UNIQUE ("from_conferenceadditionaloption_id", "to_conferenceadditionaloption_id")
)
;
ALTER TABLE "confreg_conferenceadditionaloption_mutually_exclusive" ADD CONSTRAINT "from_conferenceadditionaloption_id_refs_id_4393db99" FOREIGN KEY ("from_conferenceadditionaloption_id") REFERENCES "confreg_conferenceadditionaloption" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "confreg_conferenceadditionaloption_mutually_exclusive" ADD CONSTRAINT "to_conferenceadditionaloption_id_refs_id_4393db99" FOREIGN KEY ("to_conferenceadditionaloption_id") REFERENCES "confreg_conferenceadditionaloption" ("id") DEFERRABLE INITIALLY DEFERRED;

