FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn[standard]==0.30.6
COPY main.py .
EXPOSE 9000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","9000"]
