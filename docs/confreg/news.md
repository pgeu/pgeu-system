# News

The per conference news system is used to make shorter
announcements. It does not support paging or archiving.

All news posts will syndicate to the main website frontpage. For each
post showing up there will link back to the front page of the
conference website (as defined in the
[conference metadata](super_conference). Thus it makes sense for the
news to be published there.

In order to post a news, the user must have a News Poster Profile,
something that is currently created globally in the server (and be an
administrator for the conference).

The news posts made will all post to the conference RSS feed (at
/feeds/conf/<confurl>/).

There is also a per-user RSS feed (at /feeds/user/<userurl>/ where the
userurl is configured in the users News Poster Profile). The per user
feed is intended to be used with news aggregators that require per
person feeds.

## JSON feed

There is also a JSON format feed for the conference news (at
/feeds/conf/<confurl>/json/). This is intended to be used to feed news
on the front page of the conference website, while the website can
remain static. This feed will include *all* news, including that which
has been tagged not to be included in RSS.
