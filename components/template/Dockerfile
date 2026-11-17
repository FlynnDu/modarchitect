FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
WORKDIR /component
COPY component.py entrypoint.py file_protocol.py ./
USER 65532:65532
ENTRYPOINT ["python", "-B", "/component/entrypoint.py"]
