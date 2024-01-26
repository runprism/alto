FROM ubuntu:latest
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Linux packages
RUN apt-get update && \
    apt-get install -y software-properties-common gcc ca-certificates curl gnupg && \
    add-apt-repository -y ppa:deadsnakes/ppa

# Install Docker
RUN install -m 0755 -d /etc/apt/keyrings
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
RUN chmod a+r /etc/apt/keyrings/docker.gpg
RUN echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") $(lsb_release -cs) stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
RUN apt-get update
RUN apt-get install -y docker-ce containerd.io docker-buildx-plugin docker-compose-plugin

# Install virtual environment based on the Python version
ARG PYTHON_VERSION
RUN apt-get update
RUN if [[ "$PYTHON_VERSION" < "python3.10" ]] ; then apt-get install -y $PYTHON_VERSION $PYTHON_VERSION-env python3-distutils python3-pip python3-apt ; else apt-get install -y $PYTHON_VERSION $PYTHON_VERSION-venv python3-distutils python3-pip python3-apt ; fi

# SSH client
RUN apt-get install -y openssh-client

# Project dependencies
COPY . ./alto/
WORKDIR ./alto
RUN $PYTHON_VERSION -m venv /opt/venv
RUN . /opt/venv/bin/activate && \
    pip install -r dev_requirements.txt

ARG AWS_ACCESS_KEY_ID
ENV AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID

ARG AWS_SECRET_ACCESS_KEY
ENV AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY

ARG AWS_DEFAULT_REGION
ENV AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION

# Docker volume and server URL
ENV __ALTO_DOCKER_SERVER_URL__="unix:///var/run/docker.sock"

# # Integration tests
WORKDIR alto/tests/integration
CMD . /opt/venv/bin/activate && pytest