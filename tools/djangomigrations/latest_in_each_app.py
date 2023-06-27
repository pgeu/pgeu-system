#!/usr/bin/env python3
#
# Generate a list of (potential) dependencies on the latest migration currently in each app
#

import os
import re

if __name__ == "__main__":
    for d in sorted(os.listdir('postgresqleu')):
        dd = os.path.join('postgresqleu', d)
        ddd = os.path.join(dd, 'migrations')
        if os.path.isdir(dd) and os.path.isdir(ddd):
            try:
                print("('{}', '{}'),".format(
                    d,
                    sorted(n for n in os.listdir(ddd) if re.match(r'^\d+_.*\.py$', n))[-1][:-3],
                ))
            except IndexError:
                # No migration found
                pass
