FROM {{ base_image }}
LABEL stage=intermediate

{{ other_build_cmds }}

COPY {{ requirements_txt }} ./{{ requirements_txt }}
RUN pip install --upgrade pip && pip install -r ./{{ requirements_txt }}

{{ copy_commands }}
WORKDIR ./{{ nomad_wkdir_name }}

{{ env }}

CMD {{ cmd }}
