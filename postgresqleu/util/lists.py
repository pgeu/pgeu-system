def flatten_list(thelist):
    for i in thelist:
        if isinstance(i, list):
            for k in flatten_list(i):
                yield k
        else:
            yield i
