
import magic

# Globally load and cache the magicdb
magicdb = magic.open(magic.MIME)
magicdb.load()
