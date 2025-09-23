all: build

.stamp.base: check-env
	docker build -f Dockerfile.base -t pgeu-system-python-base:latest .
	@touch $@

.stamp.build: .stamp.base check-env
	docker compose pull
	docker compose build
	@touch $@

build: .stamp.build

start: .stamp.build check-env
	docker compose up -d --build

stop: check-env
	docker compose down

logwatch: check-env
	docker compose logs -f

clean: check-env
	docker compose down -v
	rm -rf .stamp.base .stamp.build

distclean: check-env
	docker compose down -v
	rm -rf .stamp.base .stamp.build
	docker rmi \
		pgeu-system-maintenance \
		pgeu-system-uwsgi \
		pgeu-system-httpd \
		pgeu-system-python-base \
		2> /dev/null || /bin/true

check-env:
	@sh -c '. ./.env && \
	if [ -z "$${SYSTEM_SKIN_DIRECTORY}" ]; then \
		echo "Error: SYSTEM_SKIN_DIRECTORY is not set or empty"; \
		exit 1; \
	fi; \
	if [ ! -d "$${SYSTEM_SKIN_DIRECTORY}" ]; then \
	    echo "Error: SYSTEM_SKIN_DIRECTORY=\"$${SYSTEM_SKIN_DIRECTORY}\" does not exist"; \
	    exit 1; \
	fi'

.PHONY: all check-env
