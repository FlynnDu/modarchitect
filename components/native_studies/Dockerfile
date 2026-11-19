ARG APPROVED_BASE
FROM ${APPROVED_BASE}
ARG COMPONENT_PYTHON_PREFIX=/usr/local
ENV PATH="${COMPONENT_PYTHON_PREFIX}/bin:${PATH}"
COPY entrypoint.py /app/native_study_entrypoint.py
COPY binding.json /app/binding.json
COPY vendor/ ${COMPONENT_PYTHON_PREFIX}/lib/python3.12/site-packages/pymlgrowth/model_components/
ENTRYPOINT ["python", "-IB", "/app/native_study_entrypoint.py"]
