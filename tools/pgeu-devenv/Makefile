all: build

.stamp.base:
	docker build -f Dockerfile.base -t pgeu-system-python-base:latest .
	@touch $@

.stamp.build: .stamp.base
	docker compose pull
	docker compose build
	@touch $@

build: .stamp.build

start: .stamp.build
	docker compose up -d --build

stop:
	docker compose down

logwatch:
	docker compose logs -f

clean:
	docker compose down -v
	rm -rf .stamp.base .stamp.build

distclean:
	docker compose down -v
	rm -rf .stamp.base .stamp.build
	docker rmi \
		pgeu-system-maintenance \
		pgeu-system-uwsgi \
		pgeu-system-httpd \
		pgeu-system-python-base \
		2> /dev/null || /bin/true
