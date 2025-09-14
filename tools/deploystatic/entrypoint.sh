#!/bin/sh
set -e

/deploystatic.py /source /target

if [ "$1" = "-serve" ]; then
    cd /target && python3 -m http.server 9099
fi
