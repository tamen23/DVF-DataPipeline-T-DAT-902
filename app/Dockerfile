FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# code is volume-mounted in dev (see docker-compose.yml)
EXPOSE 8501
CMD ["streamlit", "run", "Home.py", "--server.address=0.0.0.0", "--server.port=8501"]
