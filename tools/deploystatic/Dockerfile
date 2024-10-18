FROM debian:bullseye
RUN apt-get -y update && apt-get -y upgrade && apt-get -y install python3-jinja2 python3-markdown python3-dateutil && apt-get -y clean
RUN mkdir /source /target
ADD deploystatic.py /
ENTRYPOINT /deploystatic.py /source /target
