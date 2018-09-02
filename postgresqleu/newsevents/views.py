from django.shortcuts import render, get_object_or_404

import datetime

from postgresqleu.newsevents.models import News

def newsitem(request, itemid):
	item = get_object_or_404(News, pk=itemid, datetime__lte=datetime.datetime.today())
	news = News.objects.filter(datetime__lte=datetime.datetime.today())[:5]

