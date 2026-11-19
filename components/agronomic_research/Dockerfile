ARG APPROVED_BASE
FROM ${APPROVED_BASE}
ARG COMPONENT_PYTHON_PREFIX=/usr/local
ENV PATH="${COMPONENT_PYTHON_PREFIX}/bin:${PATH}"
ARG COMPONENT_CODE
ENV COMPONENT_CODE=${COMPONENT_CODE}
COPY modarchitect_agronomy/ ${COMPONENT_PYTHON_PREFIX}/lib/python3.12/site-packages/modarchitect_agronomy/
COPY file_protocol.py ${COMPONENT_PYTHON_PREFIX}/lib/python3.12/site-packages/modarchitect_agronomy/file_protocol.py
ENTRYPOINT ["python", "-IB", "-m", "modarchitect_agronomy.entrypoint"]
