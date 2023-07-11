ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG LOCAL_BUNDLE_PATH
ARG LOAD_MODEL_MODULE_PATH
ARG LOAD_PREDICT_MODULE_PATH

ENV LOCAL_BUNDLE_PATH=${LOCAL_BUNDLE_PATH} \
    LOAD_MODEL_MODULE_PATH=${LOAD_MODEL_MODULE_PATH} \
    LOAD_PREDICT_MODULE_PATH=${LOAD_PREDICT_MODULE_PATH}

WORKDIR /app

COPY ${LOCAL_BUNDLE_PATH} ${LOCAL_BUNDLE_PATH}

RUN python /app/spellbook_serve/spellbook_serve/inference/download_and_inject_bundle.py

ENV PYTHONPATH /app