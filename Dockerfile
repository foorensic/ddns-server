FROM alpine:3.20

RUN apk add --no-cache bind bind-tools pipx \
  && pipx install poetry
ENV PATH=/root/.local/bin:$PATH

COPY pyproject.toml poetry.lock api.py entrypoint.sh /app/
WORKDIR /app
RUN poetry install
RUN echo $'options { \n\
  directory \"/var/bind\"; \n\
  listen-on { any; }; \n\
  listen-on-v6 { none; }; \n\
  dnssec-validation auto; \n\
  allow-transfer { none; }; \n\
  allow-recursion { none; }; \n\
  recursion no; \n\
  auth-nxdomain no; \n\
  pid-file \"/var/run/named/named.pid\"; \n\
}; \n\
controls {}; \n\
' > /etc/bind/named.conf

RUN chmod +x entrypoint.sh

EXPOSE 53/udp 5000/tcp
ENTRYPOINT ["/app/entrypoint.sh"]
