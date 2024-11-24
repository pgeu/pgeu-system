Configuration
-------------

The traditional approach is to create a local_settings.py file under
the postgresqleu directory, a template is provided.

To allow out-of-module configuration, it is possible to instead
provide a python module pgeu_system_global_settings and extend
PYTHONPATH for it to be detected. Settings in there are loaded first,
in case the above mentioned local_settings.py is available, too, it
will override global settings.

The skin usually provides skin_settings.py and allows customization
through a similar skin_local_settings.py. These again take precedence
over global settings.

Last, a global python module pgeu_system_override_settings is
attempted to be loaded. It allows overriding any settings of the
pgeu-system or the skin.


Dependencies needed before running
----------------------------------

The following dependencies are required for manually rebuilding all the required
python modules. If using distribution packaged python modules most of them won't
be necessary, but then things usually just work out of the box and no need for
this script.

* virtualenv corresponding to python 3.7 (in path)
	* On debian, for example, this means virtualenv and python3-virtualenv packages
* c compiler and libs (typically build-essential)
* python development libraries (typically python-dev) -- for modules
* ffi development libraries (typically libffi-dev) -- for some modules
* openssl development libraries (typically libssl-dev) -- for crypto related modules
* libjpeg-dev and libpng-dev (*before* installing pillow in python)
* pg_config for postgresql, in path, for the correct version. Typically postgresql-dev package.
* uwsgi, uwsgi-plugin-python3


Database access
---------------

Access to the PostgreSQL database must work without password.


Other dependencies
------------------
For invoice generation and tickets/badges to work, the DejaVu fonts
need to be installed. The default location is
  /usr/share/fonts/truetype/ttf-dejavu/
but it can be overriden by setting FONTROOT in local_settings.py if necessary.

On debian, just install the ttf-dejavu package (fonts-dejavu on Bullseye and newer).


macOS support
-------------
All required dependencies except virtualenv can be installed via Homebrew,
virtualenv is installed with pip.
