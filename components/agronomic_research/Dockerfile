ARG APPROVED_BASE
FROM ${APPROVED_BASE}
ARG COMPONENT_CODE
ENV COMPONENT_CODE=${COMPONENT_CODE}
COPY modarchitect_agronomy/ /opt/miniconda3/envs/sumfen_mlgrowth/lib/python3.12/site-packages/modarchitect_agronomy/
COPY file_protocol.py /opt/miniconda3/envs/sumfen_mlgrowth/lib/python3.12/site-packages/modarchitect_agronomy/file_protocol.py
ENTRYPOINT ["/opt/miniconda3/envs/sumfen_mlgrowth/bin/python", "-IB", "-m", "modarchitect_agronomy.entrypoint"]
