from __future__ import absolute_import
import magic

# Globally load and cache the magicdb
magicdb = magic.open(magic.MIME)
magicdb.load()
