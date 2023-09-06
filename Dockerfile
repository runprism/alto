FROM ubuntu:latest

RUN apt-get update && \
    apt-get install -y software-properties-common gcc && \
    add-apt-repository -y ppa:deadsnakes/ppa

RUN apt-get update && \
    apt-get install -y python3.10 python3-distutils python3-pip python3-apt

RUN apt-get install -y openssh-client

COPY . ./nomad/
WORKDIR ./nomad
RUN pip install -r dev_requirements.txt

RUN pytest