#!/usr/bin/env python3

from enum import Enum
import os
from psycopg2 import connect, OperationalError, sql
import subprocess
from sys import argv, exit, stderr, stdout
from time import sleep

# Configuration via environment variables. Passwords for database
# users are expected to be provided in the .pgpass file of the current
# user executing the script.
PGDATABASE = os.environ.get("PGDATABASE", "pgeu_test")
PGUSER = os.environ.get("PGUSER", "appuser")

# Hard-coded settings matching the Docker containers.
PGEU_SYSTEM_DIR = "/srv/pgeu-system"

SUPERUSER_DSN = "user=postgres"
APP_DSN = f"user={PGUSER} dbname={PGDATABASE}"

# Simply the password 'admin' hashed and pbkdf2-ed properly, not a
# real secret.
DJANGO_ADMIN_PWD = 'pbkdf2_sha256$600000$z7O9uqatpBILenIxSRXzim$BNW6690OanF0sawBuA/XZU5kE4X4+mf3YTE7Q0W9Vvk='


def read_pgpass(username):
    """ Trivial function for reading a password from .pgpass. Likely very
        incomplete, but good enough for the simple case.
    """
    home_dir = os.environ.get("HOME", ".")
    pgpass_filename = os.path.join(home_dir, '.pgpass')
    with open(pgpass_filename, 'r') as f:
        for line in f:
            (host, port, dbname, dbuser, password) = line.strip().split(':', 5)
            if dbuser == username:
                return password
    print("WARNING: user %s not found in pgpass file" % repr(PGUSER))
    return ""


def run_django_manage(command):
    res = subprocess.run(["python3", "manage.py"] + command,
                         cwd=PGEU_SYSTEM_DIR, capture_output=True)
    return (res.returncode, res.stdout, res.stderr)


class State(Enum):
    COLLECT_STATIC_FILES = 1
    DATABASE_CREATION = 2
    CREATE_DB_USER = 3
    SETUP_DB_USER = 4
    CREATE_DB_SCHEMA = 5
    CREATE_DJANGO_ADMIN = 6
    FINAL_LOOP = 99


class App:
    def __init__(self):
        self.state = State.COLLECT_STATIC_FILES
        self.delay = None

    def extend_delay(self):
        if self.delay is None:
            self.delay = 1.0
        else:
            self.delay *= 1.3

    def advance(self, new_state):
        """ Advance the state machine to the next step
        """
        # Shoud be performed only after successful completion of the
        # previous state, so reset and eliminate delays.
        self.delay = None
        self.state = new_state

    def collect_static_files(self):
        """ Triggers Django's collectstatic command, copying static
            files over to the volume mounted into the httpd container.
        """
        (ec, out, err) = run_django_manage(["collectstatic", "--no-input"])
        if ec == 0:
            for line in err.split(b'\n'):
                if len(line) == 0:
                    continue
                if line.startswith(b'Could not load fitz library'):
                    continue
                print("WARNING: collectstatic reported error: %s (len: %d)"
                      % (repr(line), len(line)))
            for line in err.split(b'\n'):
                if len(line) == 0:
                    continue
                if line.startswith(b'Could not load fitz library'):
                    continue
                print("INFO:    collectstatic stdout: %s" % repr(line))
        else:
            print("WARNING: collecting static files failed")

    def create_database(self):
        """ Attempt to connect check for the target database. Creates it if it
            does not already exist.
        """
        try:
            print("INFO:    attempting to connect")
            conn = connect(SUPERUSER_DSN + " dbname=postgres connect_timeout=3")
            conn.autocommit = True
            cur = conn.cursor()

            # If the connection attempt succeeded, check whether the app database
            # exists, create it if it does not.
            cur.execute("SELECT COUNT(*) FROM pg_database WHERE datname = %s",
                        (PGDATABASE,))
            row = cur.fetchone()

            if row[0] == 0:
                print("INFO:    creating database '%s'" % PGDATABASE)
                cur.execute(sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(PGDATABASE)))
            else:
                print("INFO:    found existing database '%s'" % PGDATABASE)
            return True

        except OperationalError as e:
            # Get only the very first line of error
            err_msg = e.args[0].split('\n', 1)[0]
            # Assume english...
            if err_msg.endswith('no password supplied'):
                # Seems like a misconfiguration, exit
                print(stderr, "FATAL: no password supplied")
                exit(1)
            elif err_msg.endswith('timeout expired') or \
                    err_msg.endswith('Connection refused') or \
                    err_msg.endswith('Name or service not known') or \
                    err_msg.endswith('database system is starting up'):
                # Backoff, but try again (returning False will lead to
                # increasing the delay between retries).
                pass
            else:
                # Unknown error, log it as well, but optimistically
                # try again
                print(stderr, "ERROR: %s (%s)" % (e, type(e)))
            return False

        except Exception as e:
            print(stderr, "FATAL: %s (%s)" % (e, type(e)))
            exit(1)

    def create_user(self):
        try:
            conn = connect(SUPERUSER_DSN + " dbname=%s connect_timeout=3" % PGDATABASE)
            conn.autocommit = True
            cur = conn.cursor()

            # Create the app user
            cur.execute("SELECT COUNT(*) FROM pg_roles WHERE rolname = %s",
                        (PGUSER,))
            row = cur.fetchone()

            if row[0] == 0:
                print("INFO:    creating user %s" % repr(PGUSER))
                query = sql.SQL("CREATE USER {} PASSWORD %s").format(
                    sql.Identifier(PGUSER))
                cur.execute(query, (read_pgpass(PGUSER),))
            else:
                print("INFO:    found existing user %s" % repr(PGUSER))
            return True

        except Exception as e:
            print(stderr, "FATAL: %s (%s)" % (e, type(e)))
            return False

    def setup_user(self):
        try:
            conn = connect(SUPERUSER_DSN + " dbname=%s connect_timeout=3" % PGDATABASE)
            conn.autocommit = True
            cur = conn.cursor()

            # Grant the newly created user all rights required.
            print("INFO:    setting up permissions for user %s" % repr(PGUSER))
            cur.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(PGDATABASE),
                sql.Identifier(PGUSER)))
            cur.execute(sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(
                sql.Identifier(PGDATABASE),
                sql.Identifier(PGUSER)))
            cur.execute(sql.SQL("GRANT ALL ON SCHEMA {} TO {}").format(
                sql.Identifier("public"),
                sql.Identifier(PGUSER)))
            return True

        except Exception as e:
            print(stderr, "FATAL: %s (%s)" % (e, type(e)))
            return False

    def create_django_schema(self):
        """ Create the database schema for the Django application.
        """
        print("INFO:    initializing Django database schema")
        stdout.flush()
        (ec, out, err) = run_django_manage(['migrate'])

        has_auth_table = self.has_django_auth_user_table()
        if ec == 0 and has_auth_table:
            return True

        for line in out.split(b'\n'):
            print("migrate(out): %s" % repr(line))
        for line in err.split(b'\n'):
            print("migrate(err): %s" % repr(line))

        if ec == 0 and not has_auth_table:
            print(stderr, "FATAL:   auth_user does not exist")
            print(stderr, "         (schema initialization likely failed)")
        else:
            print(stderr, "FATAL:   schema initialization failed (exit code 0)")
        return False

    def create_django_admin(self):
        try:
            conn = connect(SUPERUSER_DSN + " dbname=%s connect_timeout=3" % PGDATABASE)
            conn.autocommit = True
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM auth_user WHERE is_staff AND is_active")
            row = cur.fetchone()

            if row[0] == 0:
                print("INFO:    creating Django admin user")
                cur.execute(sql.SQL("INSERT INTO auth_user (password, is_superuser, username, email, first_name, last_name, is_staff, is_active, date_joined) VALUES ({}, 't', 'admin', 'admin@example.com', '', '', 't', 't', now())").format(
                    sql.Literal(DJANGO_ADMIN_PWD)))
            else:
                print("INFO:    found an existing staff user, not inserting one")
            return True

        except Exception as e:
            print(stderr, "FATAL: %s (%s)" % (e, type(e)))
            return False

    def has_pending_migrations(self):
        """ Checks for pending migrations, without logging any
            output. Just to keep the amount of noise low. Defaults to
            return True in case of error.
        """
        (ec, out, err) = run_django_manage(["showmigrations", "-p"])
        if ec != 0:
            # Assume django has not been initialized, yet.
            return True
        lines = out.split(b'\n')
        # showmigrations outputs lines starting with '[X]' for applied
        # migrations and ones starting with '[ ]' for pending ones.
        pending_migrations = [x for x in lines if x.startswith(b'[ ]')]
        # print("INFO:    found %d pending migration steps" % len(pending_migrations))
        return len(pending_migrations) > 0

    def has_django_auth_user_table(self):
        try:
            conn = connect(SUPERUSER_DSN + " dbname=%s connect_timeout=3" % PGDATABASE)
            conn.autocommit = True
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM pg_class WHERE relname = 'auth_user'")
            row = cur.fetchone()

            if row[0] > 0:
                return True
            else:
                return False
        except Exception as e:
            print(stderr, "FATAL: %s (%s)" % (e, type(e)))
            return False

    def run(self):
        while True:
            if self.state == State.COLLECT_STATIC_FILES:
                self.collect_static_files()

                # Proceed to next step in any case, database is not dependent
                # on static files.
                self.advance(State.DATABASE_CREATION)
            elif self.state == State.DATABASE_CREATION:
                if self.create_database():
                    self.advance(State.CREATE_DB_USER)
                else:
                    self.extend_delay()
            elif self.state == State.CREATE_DB_USER:
                if self.create_user():
                    self.advance(State.SETUP_DB_USER)
                else:
                    self.extend_delay()
            elif self.state == State.SETUP_DB_USER:
                if self.setup_user():
                    self.advance(State.CREATE_DB_SCHEMA)
                else:
                    self.extend_delay()
            elif self.state == State.CREATE_DB_SCHEMA:
                if self.create_django_schema():
                    self.advance(State.CREATE_DJANGO_ADMIN)
                else:
                    print(stderr, "(aborting, restart to retry)")
                    exit(1)
            elif self.state == State.CREATE_DJANGO_ADMIN:
                self.create_django_admin()
                self.advance(State.FINAL_LOOP)
            elif self.state == State.FINAL_LOOP:
                # Repeat this step every 10 seconds to regularly keep
                # static files up to date.
                self.collect_static_files()
                self.delay = 10
            else:
                print(stderr, "FATAL: unknown state: %s" % repr(self.state))
                exit(1)

            if self.delay is not None:
                stdout.flush()
                stderr.flush()
                sleep(self.delay)

            stdout.flush()
            stderr.flush()


app = App()
app.run()
