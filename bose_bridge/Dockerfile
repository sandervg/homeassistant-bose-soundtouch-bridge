ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:latest

# py3-lxml from apk may not satisfy upnpclient's lxml version pin, in which
# case pip compiles lxml from source — which needs a C toolchain and the
# libxml2/libxslt headers. Install those as a throwaway virtual package so
# the build succeeds, then remove them to keep the runtime image small.
# (libxml2 + libxslt stay; lxml links against them at runtime.)
RUN apk add --no-cache python3 py3-pip py3-lxml libxml2 libxslt \
 && apk add --no-cache --virtual .build-deps \
        gcc musl-dev libxml2-dev libxslt-dev python3-dev \
 && pip3 install --no-cache-dir --break-system-packages \
        upnpclient==1.0.3 \
        websocket-client==1.9.0 \
        paho-mqtt==2.1.0 \
 && apk del .build-deps

COPY bridge.py /
COPY . /bose_bridge
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
