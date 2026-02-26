FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .

ENV SIGNOZ_ENDPOINT=""
ENV SIGNOZ_API_KEY=""
ENV EXECUTION_ATTRIBUTE="essvt.execution_id"
ENV POLL_INTERVAL="5"
ENV MAX_SPANS_PER_PAGE="10000"
ENV PORT="8077"

EXPOSE 8077

CMD ["rf-trace-report", "serve", "--provider", "signoz", "--port", "8077", "--no-open"]
