ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base:latest

# Use upnpclient 2.0.3, which requires lxml>=4.6.0 (no upper bound) and is
# therefore satisfied by the prebuilt py3-lxml from apk. The older 1.0.3
# pinned lxml<5, forcing pip to compile lxml 4.9.4 from source — which fails
# on the HA base image (Python 3.14, lxml 6.x, no C toolchain). Using the
# system lxml means no compile, no build tools, and a fast build on ARM too.
RUN apk add --no-cache python3 py3-pip py3-lxml \
 && pip3 install --no-cache-dir --break-system-packages \
        upnpclient==2.0.3 \
        websocket-client==1.9.0 \
        paho-mqtt==2.1.0

COPY bridge.py /
COPY . /bose_bridge
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
