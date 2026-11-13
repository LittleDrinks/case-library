FROM python:3.12-alpine

RUN addgroup -S provider && adduser -S -G provider provider
WORKDIR /app
COPY tests/e2e/fake_openai.py ./fake_openai.py
USER provider
EXPOSE 8080
CMD ["python", "fake_openai.py"]
