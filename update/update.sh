#!/usr/bin/env bash

#
# The idea:
#  * git-pull the repository
#  * uwsgi will automatically restart the application as needed
#

# Get to our root directory
UPDDIR=$(dirname $0)
cd $UPDDIR/..

# Pull changes from the it repo
git pull -q|grep -v "Already up-to-date"
