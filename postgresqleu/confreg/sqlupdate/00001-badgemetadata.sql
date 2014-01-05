/* Added RegistrationClass and RegistrationDay */
ALTER TABLE confreg_registrationtype ADD COLUMN regclass_id integer REFERENCES confreg_registrationclass(id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX confreg_registrationtype_regclass_id ON confreg_registrationtype(regclass_id);

CREATE TABLE "confreg_registrationtype_days" (
    "id" serial NOT NULL PRIMARY KEY,
    "registrationtype_id" integer NOT NULL REFERENCES "confreg_registrationtype"("id") DEFERRABLE INITIALLY DEFERRED,
    "registrationday_id" integer NOT NULL REFERENCES "confreg_registrationday" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("registrationtype_id", "registrationday_id")
)
;
