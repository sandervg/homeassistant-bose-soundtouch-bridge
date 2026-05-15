ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip py3-lxml \
 && pip3 install --no-cache-dir --break-system-packages \
        upnpclient==1.0.3 \
        websocket-client==1.9.0 \
        paho-mqtt==2.1.0

COPY bridge.py /
COPY bose_bridge /bose_bridge
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
