FROM ubuntu:latest

ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && \
    apt-get install -y software-properties-common gcc && \
    add-apt-repository -y ppa:deadsnakes/ppa

ARG PYTHON_VERSION
RUN apt-get update && \
    apt-get install -y $PYTHON_VERSION $PYTHON_VERSION-env python3-distutils python3-pip python3-apt

RUN apt-get install -y openssh-client

COPY . ./nomad/
WORKDIR ./nomad
RUN $PYTHON_VERSION -m venv /opt/venv
RUN . /opt/venv/bin/activate && \
    pip install -r dev_requirements.txt

ARG AWS_ACCESS_KEY_ID
ENV AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID

ARG AWS_SECRET_ACCESS_KEY
ENV AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY

ARG AWS_DEFAULT_REGION
ENV AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION

# Unit tests
RUN . /opt/venv/bin/activate && pytest --ignore=nomad/tests/integration

# # Integration tests
WORKDIR nomad/tests/integration
RUN . /opt/venv/bin/activate && pytest
WORKDIR ./nomad