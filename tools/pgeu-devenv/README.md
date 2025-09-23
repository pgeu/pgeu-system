# pgeu-system Docker development environment

## Introduction

This subdirectory provides a Docker compose assembly of services
allowing for an easy setup of a development environment.

[!IMPORTANT]
The Docker images (nor the Dockerfiles) are *not* meant for production
use. All passwords are trivial to guess and there's intentionally no
encryption in place.

## Quick Start

The pgeu-system needs a skin. For illustration purposes, this example
uses the main PGEU organization's skin. Other than that, of course
Docker and docker compose are required.

```shell
# Check out the pgeu-system framework
https://git.postgresql.org/git/pgeu-system.git ./pgeu-system

# Check-out the skin.
git clone https://git.postgresql.org/git/pgeu-web.git ./pgeu-web

# Configure the skin directory to use for this instance of pgeu-system.
# Alternatively, this may be persisted by writing it to
# tools/pgeu-devenv/.env so this step does not need to be repeated for
# every session.
SYSTEM_SKIN_DIRECTORY="$(pwd)/pgeu-web"

# Trigger the download and build of the Docker images
cd tools/pgeu-devenv
make

# Start the docker composition, then follow logs of all containers
make start logwatch
```

## First Steps and Conventions

The above steps will spin up four containers: a Postgres database, an
Apache webserver, the Django backend and a dedicated maintenance
container. The latter runs a script that populates the database,
initializes Django and arranges for everything required to get a
running test instance.

After about a minute or so and if all went well, a raw instance should
become available on [http://localhost:8080/](http://localhost:8080/).

An `admin` user had been created with the same password `admin`
allowing you to login to the system's
[admin&nbsp;interface]((http://localhost:8080/admin/) or the
underlying
[Django admin interface](http://localhost:8080/admin/django/).

Similarly, Postgres roles `postgres` and `appuser` were created on the
database side. Both with a password simply matching the user name. The
Django instalation uses a database named `pgeu_test`.

By defalut, PostgreSQL 17 is used. You can override this through the
environment variable `POSTGRES_VERSION` before building containers.

## Helpful Makefile Targets

While the above quick start uses `make`, it's well possible (and may
be more convenient for users familiar with the tool) to use docker
compose directly.

* `make stop` terminate the composition
* `make logwatch` shows and follows logs of all containers, often
advisable for diagnostics
* `make clean` stops the composition and removes the volumes, including the database
* `make distclean` also removes the images built

## Automated Reload and Restart

To ease development, most changes will be reflected immediately. For
example, changes in templates of the base system or the skin will have
immediate effect. The maintenance container, as long as it's running,
collects static files every 10 seconds, too.

Changes in the `pgeu_system_{global,override}_settings.py` will be
picked up immediately as well, for example, toggling `ENABLE_DEBUG`
will have immediate effect.

However, changes to the Dockerfiles, system packages or Python
dependencies may require a rebuild and restart of the containers to
take effect (i.e. `make start` or `docker compose up -d --build`).

The Postgres database lives in a named volume, thus survives a restart
of the containers (e.g. via `make stop start`). However, the `clean`
target drops the volumes and thus clears all data from the database.

## Maintenance Container

For many administrative tasks, Django offers a `manage.py`
script. This is used automatically in the background during
initialization and for regular static file collection, but may also be
invoked manually.

```shell
# Show Django management help.
docker compose exec -it maintenance ./manage.py help

# Load the country fixtures.
docker compose exec -it maintenance ./manage.py loaddata initial_data.xml
docker compose exec -it maintenance ./manage.py loaddata europe_countries.json
```

## Database

Through the maintenance container, it's also easy to connect to the
database Django uses:

```shell
docker compose exec maintenance psql pgeu_test
```

## Troubleshooting

In case something goes wrong, it's recommended to first check the logs
of the maintenance container.

```shell
docker compose logs -f maintenance
```
