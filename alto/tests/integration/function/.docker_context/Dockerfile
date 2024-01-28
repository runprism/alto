FROM python:3.10.8-slim-bullseye
LABEL stage=intermediate



COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r ./requirements.txt

COPY function/ ./function
WORKDIR ./function

ENV AWS_ACCESS_KEY_ID=AKIAQ63K4C3PGSTD7EAN
ENV AWS_SECRET_ACCESS_KEY=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
ENV AWS_DEFAULT_REGION=us-east-1

CMD python -c 'from main import write_txt_file; write_txt_file(platform="darwin", python_version="3.10.12")'