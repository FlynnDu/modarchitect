FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
WORKDIR /component
COPY template/file_protocol.py components/template/
COPY chain_tables.py components/
COPY forecast_join/component.py forecast_join/entrypoint.py components/forecast_join/
USER 65532:65532
ENTRYPOINT ["python", "-B", "-m", "components.forecast_join.entrypoint"]
