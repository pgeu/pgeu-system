FROM debian:bookworm
RUN apt-get -y update && apt-get -y upgrade && apt-get -y install python3-jinja2 python3-markdown python3-dateutil python3-reportlab fonts-dejavu-core fonts-dejavu-extra python3-qrcode && apt-get -y clean
ADD postgresqleu /postgresqleu
ADD tools/deploystatic/jinjapdf-docker/entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]
