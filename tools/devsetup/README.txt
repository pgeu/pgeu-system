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
* libqrencode-dev
* uwsgi, uwsgi-plugin-python3


Database access
---------------

Access to the PostgreSQL database must work without password.


Other dependencies
------------------
For invoice generation to work, DejaVu needs to be installed in
/usr/share/fonts/truetype/ttf-dejavu/

On debian, just install ttf-dejavu.


macOS support
-------------
All required dependencies except virtualenv can be installed via Homebrew,
virtualenv is installed with pip.


Dockerfile
----------

A Dockerfile is present to showcase the needed installation and how to run the
app. The base image is based on debian buster, which can also be used for
development should one wishes to. The admin name for the app and the database,
as well as the name of the database itself is set to 'pgeusystem'.

The created user, pgeusystem, can be mapped to the userid and groupid of the
host user that owns the base directory that the app is installed. It is
recommended that it is not root. That allows for the base directory to be
mounted in the container and changes to be able to propagate from host to
container without rebuilding the image.

A typical usecase would be to build the docker image, via:
	$  docker build -t pgeusystem-image \
		--build-arg USER_ID=$(id -u) \
		--build-arg GROUP_ID=$(id -g) \
		-f ./tools/devsetup/Dockerfile .
from the base directory.

Then run said image in the background using the host's network and binding the
base directory in shared mode, via:
	$ docker run \
		--mount type=bind,source="$(pwd)",target=/opt/pgeusystem/app,bind-propagation=shared \
		--name pgeusystem-image \
		--network host \
		-d \
		pgeusystem-image

If the above commands are successfull then one can reach the index page of the
app in http://localhost:8012

If the user so wishes, can reach the database in the running container via:
	$ psql -h localhost -U pgeusystem pgeusystem

Finally to stop the running image from running, issue:
	$ docker container stop pgeusystem-image
