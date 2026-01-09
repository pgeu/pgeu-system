from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.utils import formatdate, formataddr, format_datetime
from email.header import Header
from email import encoders, charset
from email.parser import Parser
import email.policy

from postgresqleu.util.context_processors import settings_context
from postgresqleu.util.markup import pgmarkdown
from postgresqleu.confreg.jinjafunc import render_jinja_template, render_jinja_conference_mail

from django.utils import timezone

from .models import QueuedMail


# Send an email with the contents from a jinja template
def send_template_mail(sender, receiver, subject, templatename, templateattr={}, attachments=None, bcc=None, sendername=None, receivername=None, suppress_auto_replies=True, is_auto_reply=False, sendat=None, conference=None):
    (plain, html, htmlattachments) = render_jinja_conference_mail(conference, templatename, templateattr, subject)

    _internal_send_mail(
        sender, receiver, subject,
        plain.lstrip(), attachments, htmlattachments, bcc, sendername, receivername,
        suppress_auto_replies, is_auto_reply, sendat, html.lstrip(),
    )


def _encoded_email_header(name, email):
    if name:
        return formataddr((str(Header(name, 'utf-8')), email))
    return email


# Send an email with no templating
def send_simple_mail(sender, receiver, subject, msgtxt, attachments=None, bcc=None, sendername=None, receivername=None, suppress_auto_replies=True, is_auto_reply=False, sendat=None):
    _internal_send_mail(sender, receiver, subject, msgtxt, attachments, None, bcc, sendername, receivername, suppress_auto_replies, is_auto_reply, sendat)


# Default for utf-8 in python is to encode subject with "shortest" and body with "base64". For our texts,
# make it always quoted printable, for easier reading and testing.
_utf8_charset = charset.Charset('utf-8')
_utf8_charset.header_encoding = charset.QP
_utf8_charset.body_encoding = charset.QP


def _add_attachments(attachments, msg, isinline):
    for filename, contenttype, content in attachments:
        main, sub = contenttype.split('/')
        part = MIMENonMultipart(main, sub)
        part.set_payload(content)
        part.add_header('Content-Disposition', '{}; filename="{}"'.format('inline' if isinline else 'attachment', filename))
        part.add_header('Content-ID', '<{}@img>'.format(filename))
        encoders.encode_base64(part)
        msg.attach(part)


def _internal_send_mail(sender, receiver, subject, msgtxt, attachments=None, htmlattachments=None, bcc=None, sendername=None, receivername=None, suppress_auto_replies=True, is_auto_reply=False, sendat=None, htmlbody=None):
    # attachment format, each is a tuple of (name, mimetype,contents)
    # content should be *binary* and not base64 encoded, since we need to
    # use the base64 routines from the email library to get a properly
    # formatted output message

    if htmlbody:
        mpart = MIMEMultipart("alternative")
        mpart.attach(MIMEText(msgtxt, _charset=_utf8_charset))
        if htmlattachments:
            hpart = MIMEMultipart("related")
            hpart.attach(MIMEText(htmlbody, "html", _charset=_utf8_charset))
            _add_attachments(htmlattachments, hpart, True)
            mpart.attach(hpart)
        else:
            mpart.attach(MIMEText(htmlbody, "html", _charset=_utf8_charset))
    else:
        # Plaintext only
        mpart = MIMEText(msgtxt, _charset=_utf8_charset)

    if attachments:
        msg = MIMEMultipart()
        msg.attach(mpart)
        _add_attachments(attachments, msg, False)
    else:
        msg = mpart

    msg['Subject'] = subject
    msg['To'] = _encoded_email_header(receivername, receiver)
    msg['From'] = _encoded_email_header(sendername, sender)
    if sendat is None:
        msg['Date'] = formatdate(localtime=True)
    else:
        msg['Date'] = format_datetime(sendat)
    if suppress_auto_replies:
        # Do our best to set some headers to indicate that auto-replies like out of office
        # messages should not be sent to this email.
        msg['X-Auto-Response-Suppress'] = 'All'
        if is_auto_reply:
            msg['Auto-Submitted'] = 'auto-replied'
        else:
            msg['Auto-Submitted'] = 'auto-generated'

    # Just write it to the queue, so it will be transactionally rolled back
    QueuedMail(
        sender=sender,
        receiver=receiver,
        subject=subject,
        fullmsg=msg.as_string(),
        sendtime=sendat or timezone.now(),
    ).save()

    # Any bcc is just entered as a separate email
    if bcc:
        if type(bcc) is list or type(bcc) is tuple:
            bcc = set(bcc)
        else:
            bcc = set((bcc, ))

        for b in bcc:
            QueuedMail(
                sender=sender,
                receiver=b,
                subject=subject,
                fullmsg=msg.as_string(),
                sendtime=sendat or timezone.now(),
            ).save()


def parse_mail_content(fullmsg):
    # We only try to parse the *first* piece, because we assume
    # all our emails are trivial.
    try:
        parser = Parser(policy=email.policy.default)
        parsed_msg = parser.parsestr(fullmsg)
        htmlbody = parsed_msg.get_body(['html', ])
        return (
            parsed_msg,
            parsed_msg.get_body(['plain', 'html', ]).get_payload(decode=True),
            htmlbody and htmlbody.get_payload(decode=True) or b'No HTML body found',
        )
    except Exception as e:
        raise Exception("Failed to get body: %s" % e)


def recursive_parse_attachments_from_message(container, disposition='attachment'):
    if container.is_multipart():
        for p in container.get_payload():
            if p.get_params() is None:
                continue
            yield from recursive_parse_attachments_from_message(p, disposition)
    elif container.get_content_type() != 'text/plain':
        if container.get_content_disposition() == disposition or not disposition:
            idwrap = container.get_all('content-id')
            id = idwrap[0] if idwrap else container.get_filename()
            yield (id, container.get_filename(), container.get_content_type(), container.get_payload(decode=True))
