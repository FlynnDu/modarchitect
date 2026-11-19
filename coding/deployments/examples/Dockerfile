FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY modarchitect-*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/modarchitect-*.whl && rm /tmp/modarchitect-*.whl
RUN python -c "import modarchitect.api, modarchitect.input_sources.soil; from modarchitect.study_templates import templates; assert len(templates()) == 20"
USER 65532:65532
CMD ["python", "-m", "uvicorn", "modarchitect.api:app", "--host", "0.0.0.0", "--port", "8000"]
