FROM {{ base_image }}
LABEL stage=intermediate

{{ image_build_cmds }}

COPY {{ requirements_txt }} ./requirements.txt
RUN pip install --upgrade pip && pip install -r ./{{ requirements_txt }}

{{ mount_cmds }}
WORKDIR ./{{ alto_wkdir_name }}

{{ env }}

CMD {{ cmd }}
