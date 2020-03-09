from django.shortcuts import render, get_object_or_404
from django.core import paginator
from django.utils import timezone

import datetime

from postgresqleu.newsevents.models import News


def newsitem(request, itemid):
    item = get_object_or_404(News.objects.select_related('author'),
                             pk=itemid, datetime__lte=timezone.now())
    news = News.objects.filter(datetime__lte=timezone.now(), inarchive=True)[:10]

    return render(request, 'newsevents/news.html', {
        'item': item,
        'news': news,
    })


def newsarchive(request):
    news = News.objects.filter(datetime__lte=timezone.now(), inarchive=True)[:10]
    allnews = News.objects.filter(datetime__lte=timezone.now(), inarchive=True)

    p = paginator.Paginator(allnews, 15)

    page = request.GET.get('page', 1)
    try:
        newspage = p.page(page)
    except paginator.PageNotAnInteger:
        newspage = p.page(1)
    except paginator.EmptyPage:
        newspage = p.page(p.num_pages)

    return render(request, 'newsevents/archive.html', {
        'news': news,
        'newspage': newspage,
    })
