ARG APPROVED_BASE
FROM ${APPROVED_BASE}
COPY entrypoint.py /app/native_study_entrypoint.py
COPY binding.json /app/binding.json
COPY vendor/ /opt/miniconda3/envs/sumfen_mlgrowth/lib/python3.12/site-packages/pymlgrowth/model_components/
ENTRYPOINT ["/opt/miniconda3/envs/sumfen_mlgrowth/bin/python", "-IB", "/app/native_study_entrypoint.py"]
