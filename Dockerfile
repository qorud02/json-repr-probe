FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/qorud02/json-repr-probe" \
      org.opencontainers.image.description="Find JSON CLI bugs caused by member order, whitespace and character escapes." \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY json_repr_probe/ /app/json_repr_probe/
COPY LICENSE /app/LICENSE
RUN python -m json_repr_probe --version \
    && mkdir /work

USER 10001:10001
WORKDIR /work
ENTRYPOINT ["python", "-P", "-m", "json_repr_probe"]
CMD ["--help"]
