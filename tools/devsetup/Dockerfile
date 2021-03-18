# Download base image Debian Buster as the biggest installations run there
FROM  debian:buster-slim

# LABEL the image
LABEL maintainer="pgeu-system@lists.postgresql.eu"
LABEL version="0.1"
LABEL description="This is a base development environment for the \
PostgreSQL Europe Conference Management System"

# Arguments to create user for file mounting
ARG USER_ID
ARG GROUP_ID

# Avoid interactive packages
ARG DEBIAN_FRONTEND=noninteractive

# Update to the latest version and install basic packages
RUN apt-get update && apt-get -y install apt-utils
RUN apt-get update && apt-get -y install wget \
										 sudo \
										 apt-utils \
										 gnupg gnupg1 gnupg2 \
										 lsb-release

# Install postgres, start with the required repo
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc  > /tmp/key
RUN sudo apt-key add /tmp/key
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ `lsb_release -cs`-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list

# Update again and install postgres
RUN apt-get update && apt-get install -y \
	postgresql-13 \
	postgresql-client-13 \
	postgresql-server-dev-13

# Make it part of the path
ENV PATH="/usr/lib/postgresql/13/bin:${PATH}"

# Install the rest of the essential packages
RUN apt-get update && apt-get install -y \
	python3.7 \
	virtualenv \
	python3-virtualenv \
	build-essential \
	python-dev \
	libffi-dev \
	libssl-dev \
	libjpeg-dev \
	libpng-dev \
	libqrencode-dev \
	uwsgi \
	uwsgi-plugin-python3 \
	python3-pip \
	python3-cairosvg \
	python3-qrencode \
	ttf-dejavu

# Create the user to be used with bash for interactive sessions
RUN addgroup --gid $GROUP_ID pgeusystem
RUN useradd -s /bin/bash --gid $GROUP_ID -G sudo,postgres,root --uid $USER_ID pgeusystem

# Create the directories to be used and adjust the ownership
WORKDIR /opt/pgeusystem/setup
WORKDIR /opt/pgeusystem/pgdata
WORKDIR /opt/pgeusystem/app
RUN chown -R pgeusystem.pgeusystem /opt/pgeusystem

# Create the datadir, db and user for out app
USER pgeusystem
RUN pg_ctl -D /opt/pgeusystem/pgdata initdb
RUN pg_ctl -D /opt/pgeusystem/pgdata -l /opt/pgeusystem/pgdata/logfile start \
	&& psql -c 'CREATE DATABASE pgeusystem' postgres \
	&& psql -c 'GRANT ALL PRIVILEGES ON DATABASE pgeusystem TO pgeusystem' pgeusystem \
	&& pg_ctl -D /opt/pgeusystem/pgdata stop

# Create a file to run the app, expects that the volume is mounted
WORKDIR /opt/pgeusystem/setup
USER pgeusystem
RUN echo "#!/bin/bash\n\
		  set -e\n\
		  pg_ctl -D /opt/pgeusystem/pgdata -l /opt/pgeusystem/pgdata/logfile start\n\
		  pushd /opt/pgeusystem/app/\n\
	      ./tools/devsetup/dev_setup.sh localhost 5432 pgeusystem pgeusystem\n\
		  uwsgi --ini ./devserver-uwsgi.ini\n" > startup.sh
RUN chmod +x startup.sh

# Set the workdirectory
WORKDIR /opt/pgeusystem/app

CMD ["../setup/startup.sh"]
