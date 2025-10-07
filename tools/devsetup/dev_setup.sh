#!/bin/bash

set -e

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <hostname> <port> <database> <user>"
    exit
fi

PGH=$1
PGP=$2
PGD=$3
PGU=$4

echo "Host/path to postgres: $PGH"
echo "                 Port: $PGP"
echo "             Database: $PGD"
echo "                 User: $PGU"

echo "Verifying postgres connection..."
psql -w "host=$PGH port=$PGP dbname=$PGD user=$PGU" -c "SELECT 1" >/dev/null

# Start from script directory to be safe!
cd "${0%/*}"

virtualenv --python=python3 venv_dev
# Newer virtualenvs can't handle symlinks, so create a tiny binary
rm -f python
cat >../../python <<EOF
#!/bin/sh
exec $(dirname $(realpath $0))/../../tools/devsetup/venv_dev/bin/python "\$@"
EOF
chmod +x ../../python
../../python -m pip install -r dev_requirements.txt

# Configure the test instance. This is done through the traditional
# approach with local_settings.py here. An alternative would be to
# write the very same content to
# venv_dev/lib/python3.11/site-packages/pgeu_system_global_settings.py
cd ../..
cat > postgresqleu/local_settings.py <<EOF
DEBUG=True
DISABLE_HTTPS_REDIRECTS=True
DATABASES={
 'default': {
   'ENGINE': 'django.db.backends.postgresql_psycopg2',
   'NAME': '$PGD',
   'HOST': '$PGH',
   'PORT': '$PGP',
   'USER': '$PGU',
 }
}
SECRET_KEY='reallysecretbutwhocares'
SERVER_EMAIL='root@localhost'
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
SITEBASE="http://localhost:8012/"
EOF

./python manage.py migrate

cat tools/devsetup/devserver-uwsgi.ini.tmpl | sed -e "s#%DJANGO%#$(pwd)/tools/devsetup/venv_dev#g" > devserver-uwsgi.ini

echo ""
echo "Creating a django superuser, and setting password!"
result=`psql -A -n -q -t -w -X -h $PGH -p $PGP -d $PGD -U $PGU -c "SELECT COUNT(*) FROM public.auth_user WHERE is_superuser IS true"`
echo ""
if [ $result -eq "0" ];
then
    echo "creating a Django superuser, and setting password!"
    ./python manage.py createsuperuser
else
    echo "superuser already exists, skipping"
fi


echo "All ready to go. To start the development server, go to"
pwd
echo "and run:"
echo "uwsgi --ini devserver-uwsgi.ini"
echo ""
echo "or for a slightly more limited version:"
echo "./python manage.py runserver"
