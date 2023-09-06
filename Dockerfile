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

ENV AWS_ACCESS_KEY_ID=AKIAQ63K4C3PKSV4KA6K
ENV AWS_SECRET_ACCESS_KEY=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
ENV AWS_DEFAULT_REGION=us-east-1
