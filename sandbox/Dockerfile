FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libx11-6 libexpat1 \
    && rm -rf /var/lib/apt/lists/*
