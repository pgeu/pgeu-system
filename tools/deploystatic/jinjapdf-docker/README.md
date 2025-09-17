Docker container for jinjapdf
=============================

If you have trouble running jinjapdf locally, for example because of
dependencies, this docker container can be used to simplify it.

To pull the container, just run:

```
docker pull ghcr.io/pgeu/pgeusys-jinjapdf
```

To test out a badge file in a repository, create an attendee report in
JSON format and store it as `attendees.json` in the root of the
repository (do *not* commit that!), and then run:

```
docker run --rm -it -u `id -u` -v <repo>:/mnt pgeusys-jinjapdf badge /mnt /mnt/attendees.json /mnt/badges.pdf
```

This will run the jinjapdf script and create a file called badges.pdf
in the root of your repo.
