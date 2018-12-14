def flatten_list(l):
    for i in l:
        if isinstance(i, list):
            for k in flatten_list(i):
                yield k
        else:
            yield i
