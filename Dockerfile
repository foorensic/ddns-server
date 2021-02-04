FROM alpine:latest

RUN apk add --no-cache bind bind-tools python3 \
  && python3 -m ensurepip \
  && pip3 install -U pip

# API
COPY ddns-api/ /app
WORKDIR /app
RUN pip3 install -r requirements.txt

# DNS
COPY setup.sh /
RUN chmod +x /setup.sh
COPY named.conf /etc/bind/named.conf

EXPOSE 53/udp 5000/tcp

ENTRYPOINT "/setup.sh"
