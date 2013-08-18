#!/usr/bin/env bash

#
# The idea:
#  * git-pull the repository
#  * if the repository has changed, kill the django processes causing a restart
#
# Would be even better if we could touch it only after actual code files have changed,
# but this will do fine for now.

# This is where git lives on freebsd at least
PATH=$PATH:/usr/local/bin

# Get to our root directory
UPDDIR=$(dirname $0)
cd $UPDDIR/..

# Pull changes from the it repo
git pull -q|grep -v "Already up-to-date"

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
sudo pkill -f postgresqleu/manage.py

# Update the file listing the latest update
mv -f /tmp/pgeu.update update/lastupdate

