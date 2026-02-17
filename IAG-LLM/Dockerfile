FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-web.txt /app/
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

COPY . /app

EXPOSE 8000
CMD ["python", "backend/manage.py", "runserver", "0.0.0.0:8000"]
