FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
WORKDIR /component
COPY tabular_learning/requirements.txt ./
COPY wheels/ /wheels/
RUN python -m pip install --no-index --find-links=/wheels --require-hashes -r requirements.txt && rm -rf /wheels
COPY template/file_protocol.py components/template/
COPY chain_tables.py components/
COPY multivariate_regression/component.py components/multivariate_regression/
COPY research_runtime/linear.py components/research_runtime/
COPY tabular_learning/component.py tabular_learning/estimators.py tabular_learning/entrypoint.py components/tabular_learning/
ARG COMPONENT_CODE
ENV COMPONENT_CODE=$COMPONENT_CODE OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
ENTRYPOINT ["python", "-B", "-m", "components.tabular_learning.entrypoint"]
