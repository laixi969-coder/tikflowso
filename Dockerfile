FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72
RUN python -m pip install --no-cache-dir --only-binary=:all: pywhispercpp==1.5.1
COPY --from=mwader/static-ffmpeg:7.1.1@sha256:11a44711684c0b9f754c047dcd64235b8b52deab251bd0e0a86f22faa160749c /ffmpeg /ffprobe /usr/local/bin/
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TIKFLOWSO_ENV_FILE=/app/.data/service.env
COPY *.py ./
COPY web/ web/
COPY extension/ extension/
COPY qa/samples/vision/ qa/samples/vision/
USER 65532:65532
CMD ["python", "server.py", "--host", "0.0.0.0"]
