alter table confreg_conferenceregistration add column "vouchercode" varchar(100) NOT NULL default '';
alter table confreg_conferenceregistration alter column vouchercode drop default;
alter table confreg_registrationtype add column specialtype varchar(5);
alter table confreg_conference drop column autoapprove;

CREATE TABLE "confreg_conference_staff" (
    "id" serial NOT NULL PRIMARY KEY,
    "conference_id" integer NOT NULL REFERENCES "confreg_conference"("id") DEFERRABLE INITIALLY DEFERRED,
    "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("conference_id", "user_id")
)
;
