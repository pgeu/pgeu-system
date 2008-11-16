#!/usr/bin/env bash

#
# The idea:
#  * git-pull the repository
#  * if the repository has changed, touch django.wsgi, causing apache to reload
#
# Would be even better if we could touch it only after actual code files have changed,
# but this will do fine for now.

# Get to our root directory
UPDDIR=$(dirname $0)
cd $UPDDIR/..

# Pull changes from the it repo
git pull -q

# Figure out if something changed
git log -n1 --pretty=oneline > /tmp/pgeu.update
if [ -f "update/lastupdate" ]; then
   cmp update/lastupdate /tmp/pgeu.update
   if [ "$?" == "0" ]; then
      # No change, so don't reload
      rm -f /tmp/pgeu.update
      exit
   fi
fi

# Cause reload
echo Reloading website due to updates
touch postgresqleu/django.wsgi

# Update the file listing the latest update
mv -f /tmp/pgeu.update update/lastupdate

