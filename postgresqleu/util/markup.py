import markdown


# We do pure markdown and don't bother doing any filtering on the content
# as for now anybody entering markdown is considered trusted.
def pgmarkdown(value):
    return markdown.markdown(value, extensions=['tables', ])


# Wrapper class for a string that we want linebreaks to be visible in
class LineBreakString(str):
    pass
