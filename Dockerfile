FROM scratch AS wheelhouse

FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS sqlite-arm64
ADD --checksum=sha256:61a67f7085f497fa7622c6e1ae8611b8b2796a2eca70dcecc8d9124ca4f0d46b https://conda.anaconda.org/conda-forge/linux-aarch64/libsqlite-3.54.1-hd26f1b6_101.conda /tmp/sqlite.conda

FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS sqlite-amd64
ADD --checksum=sha256:c294029f893d05286f1061bbab85b820f1eea73dd859af4bcc619197bcc34810 https://conda.anaconda.org/conda-forge/linux-64/libsqlite-3.54.1-h0737f62_101.conda /tmp/sqlite.conda

FROM sqlite-${TARGETARCH} AS sqlite-build
COPY build/extract_sqlite.py /tmp/extract_sqlite.py
RUN python /tmp/extract_sqlite.py

FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9
COPY requirements.lock /tmp/tikflowso-requirements.lock
RUN --mount=type=bind,from=wheelhouse,target=/opt/wheels \
    if ls /opt/wheels/*.whl >/dev/null 2>&1; then export PIP_NO_INDEX=1 PIP_FIND_LINKS=/opt/wheels; fi \
    && python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/tikflowso-requirements.lock \
    && python -m pip check
COPY --from=mwader/static-ffmpeg:7.1.1@sha256:11a44711684c0b9f754c047dcd64235b8b52deab251bd0e0a86f22faa160749c /ffmpeg /ffprobe /usr/local/bin/
COPY --from=sqlite-build /tmp/libsqlite3.so.0 /opt/tikflowso-sqlite/libsqlite3.so.0
ENV LD_LIBRARY_PATH=/opt/tikflowso-sqlite
RUN python -c "import sqlite3; assert sqlite3.sqlite_version_info == (3,54,1)"
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TIKFLOWSO_ENV_FILE=/app/.data/service.env
COPY *.py ./
COPY web/ web/
COPY extension/ extension/
COPY qa/samples/vision/ qa/samples/vision/
USER 65532:65532
CMD ["python", "server.py", "--host", "0.0.0.0"]
