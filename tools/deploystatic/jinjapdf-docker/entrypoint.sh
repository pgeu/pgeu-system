#!/bin/bash
set -e
cd /postgresqleu
export PYTHONPATH=.
python3 confreg/jinjapdf.py --fontroot /usr/share/fonts/truetype/dejavu $*
