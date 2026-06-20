ARG BUILD_FROM
FROM ${BUILD_FROM}

# Runtime libs for lxml + temporary build deps so pip can compile lxml 4.x
# (upnpclient pins lxml<5, but the HA base image now ships Python 3.14 with
# only lxml 6 available as an apk package, so pip falls back to building from
# source). The build-deps virtual package is removed at the end to keep the
# image small.
RUN apk add --no-cache python3 py3-pip libxml2 libxslt \
 && apk add --no-cache --virtual .build-deps \
        gcc musl-dev libxml2-dev libxslt-dev python3-dev \
 && pip3 install --no-cache-dir --break-system-packages \
        upnpclient \
        websocket-client \
        paho-mqtt \
 && apk del .build-deps

COPY bridge.py /
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
