from itertools import cycle


def luhn(s):
    factors = cycle([2, 1])

    def partial(num, factor):
        q, r = divmod(num * factor, 10)
        return q + r

    f = sum(partial(int(c), f) for c, f in zip(s, factors))
    return -f % 10
