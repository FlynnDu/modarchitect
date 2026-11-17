FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
WORKDIR /component
COPY multivariate_regression/requirements.txt ./
RUN --mount=type=bind,from=wheels,target=/wheels \
    python -m pip install --no-index --find-links=/wheels --require-hashes -r requirements.txt
COPY template/file_protocol.py components/template/
COPY multivariate_regression/component.py multivariate_regression/entrypoint.py components/multivariate_regression/
ENV OPENBLAS_NUM_THREADS=1
USER 65532:65532
ENTRYPOINT ["python", "-B", "-m", "components.multivariate_regression.entrypoint"]
