import re

# Functions for working with shortened posts

# This does not appear to match everything in any shape or form, but we are only
# using it against URLs that we have typed in ourselves, so it should be easy
# enough.
# Should be in sync with regexp in js/admin.js
_re_urlmatcher = re.compile(r'\bhttps?://\S+', re.I)

# This is currently the value for Twitter and the default for Mastodon, so just
# use that globally for now.
_url_shortened_len = 23
_url_counts_as_characters = "https://short.url/{}".format((_url_shortened_len - len("https://short.url/")) * 'x')


def get_shortened_post_length(txt):
    return len(_re_urlmatcher.sub(_url_counts_as_characters, txt))


# Truncate a text, taking into account URL shorterners. WIll not truncate in the middle of an URL,
# but right now will happily truncate in the middle of a word (room for improvement!)
def truncate_shortened_post(txt, maxlen):
    matches = list(_re_urlmatcher.finditer(txt))

    if not matches:
        # Not a single url, so just truncate
        return txt[:maxlen]

    firststart, firstend = matches[0].span()
    if firststart + _url_shortened_len > maxlen:
        # We hit the size limit before the url or in the middle of it, so skip the whole url
        return txt[:firststart]

    inlen = firstend
    outlen = firststart + _url_shortened_len
    for i, curr in enumerate(matches[1:]):
        prevstart, prevend = matches[i].span()
        currstart, currend = curr.span()

        betweenlen = currstart - prevend
        if outlen + betweenlen > maxlen:
            # The limit was hit in the text between urls
            left = maxlen - outlen
            return txt[:inlen + (maxlen - outlen)]
        if outlen + betweenlen + _url_shortened_len > maxlen:
            # The limit was hit in the middle of this URL, so include all the text
            # up to it, but skip the url.
            return txt[:inlen + betweenlen]

        # The whole URL fit
        inlen += betweenlen + currend - currstart
        outlen += betweenlen + _url_shortened_len

    return txt[:inlen + (maxlen - outlen)]
