from django.contrib.syndication.views import Feed
from django.http import Http404
from django.template.defaultfilters import slugify
from django.shortcuts import get_object_or_404
from django.conf import settings

from .models import News, NewsPosterProfile

import datetime

from postgresqleu.util.db import exec_to_dict


class LatestNews(Feed):
    title = "News - %s" % settings.ORG_NAME
    link = "/"
    description_template = "pieces/news_description.html"

    def get_object(self, request, what):
        if what == 'news':
            return None
        elif what.startswith('user/'):
            a = get_object_or_404(NewsPosterProfile, urlname=what.split('/')[1])
            self.item_author_name = a.fullname
            return a
        raise Http404("Feed not found")

    def description(self, obj):
        if obj:
            return "The latest news from {0} by {1}".format(settings.ORG_NAME, obj.fullname)
        else:
            return "The latest news from {0}".format(settings.ORG_NAME)

    def items(self, obj):
        # Front page news is a mix of global and conference news, possibly
        # filtered by NewsPosterProfile.
        if obj is None:
            extrafilter = ""
            params = {}
        else:
            extrafilter = " AND author_id=%(authorid)s"
            params = {
                'authorid': obj.pk,
            }

        return exec_to_dict("""WITH main AS (
  SELECT id, NULL::text as link, datetime, title, summary
  FROM newsevents_news
  WHERE datetime<CURRENT_TIMESTAMP AND inrss {0}
  ORDER BY datetime DESC LIMIT 10),
conf AS (
  SELECT n.id, c.confurl AS link, datetime, c.conferencename || ' - ' || title AS title, summary
  FROM confreg_conferencenews n
  INNER JOIN confreg_conference c ON c.id=conference_id
  WHERE datetime<CURRENT_TIMESTAMP AND inrss {0}
  ORDER BY datetime DESC LIMIT 10)
SELECT id, link, datetime, title, summary, true AS readmore FROM main
UNION ALL
SELECT id, link, datetime, title, summary, false FROM conf
ORDER BY datetime DESC LIMIT 10""".format(extrafilter), params)

    def item_title(self, news):
        return news['title']

    def item_link(self, news):
        if news['link']:
            return '{0}##{1}'.format(news['link'], news['id'])
        else:
            return '{0}/news/{1}-{2}/'.format(
                settings.SITEBASE,
                slugify(news['title']),
                news['id'],
            )

    def item_pubdate(self, news):
        return news['datetime']
