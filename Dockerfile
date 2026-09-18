FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY start.py ./start.py
ENV PORT=8000 GEMINI_MODEL=gemini-flash-lite-latest
EXPOSE 8000
CMD ["python", "start.py"]
