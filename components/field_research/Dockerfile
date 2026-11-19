ARG APPROVED_BASE
FROM ${APPROVED_BASE}
WORKDIR /component
COPY field_research/entrypoint.py field_research/weather.py field_research/ndvi.py field_research/calendar.py components/field_research/
COPY template/file_protocol.py components/template/
COPY chain_tables.py components/chain_tables.py
ARG COMPONENT_CODE
ENV COMPONENT_CODE=${COMPONENT_CODE}
USER 65532:65532
ENTRYPOINT ["python", "-B", "-m", "components.field_research.entrypoint"]
