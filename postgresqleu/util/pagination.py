from django.core.paginator import Paginator, EmptyPage, InvalidPage


def simple_pagination(request, objects, num_per_page):
    paginator = Paginator(objects, num_per_page)
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    try:
        queryset = paginator.page(page)
    except (EmptyPage, InvalidPage):
        queryset = paginator.page(paginator.num_pages)

    if paginator.num_pages > 15:
        if page < paginator.num_pages - 13:
            firstpage = max(1, page - 7)
            lastpage = firstpage + 15
        else:
            lastpage = min(paginator.num_pages + 1, page + 8)
            firstpage = lastpage - 15
        page_range = list(range(firstpage, lastpage))
    else:
        page_range = paginator.page_range

    return (queryset, paginator, page_range)
