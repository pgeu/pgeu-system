# File upload

For each conference it is possible to upload external data in a
structured format that will be merged with the data in the
system. Each data has its own provider and format, explained below.

### Video links

Video links can be uploaded in a format that looks like:

```
{
  "sessions": {
    "<sessionid>": {
      "<provider>": "<link>",
      ...
    }
    ...
  }
}
```
