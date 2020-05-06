from postgresqleu.util.db import exec_to_list
from postgresqleu.mailqueue.util import send_simple_mail


def get_sponsor_dashboard_data(conference):
    return (
        ["Level", "Confirmed", "Unconfirmed"],
        exec_to_list("SELECT l.levelname, count(s.id) FILTER (WHERE confirmed) AS confirmed, count(s.id) FILTER (WHERE NOT confirmed) AS unconfirmed FROM confsponsor_sponsorshiplevel l LEFT JOIN confsponsor_sponsor s ON s.level_id=l.id WHERE l.conference_id=%(confid)s GROUP BY l.id ORDER BY levelcost", {'confid': conference.id, })
    )


def send_conference_sponsor_notification(conference, subject, message):
    if conference.sponsoraddr:
        send_simple_mail(conference.sponsoraddr,
                         conference.sponsoraddr,
                         subject,
                         message,
                         sendername=conference.conferencename)
