FROM python:3.14-slim

WORKDIR /sentry

COPY browser/ /sentry/browser/
COPY native/ /sentry/native/
COPY core/ /sentry/core/

RUN apt-get update && apt-get install -y --no-install-recommends adb
RUN pip install --no-cache-dir frida-tools
RUN python3 /sentry/core/agent/build_agent.py --root /sentry --out /sentry/build/agent.js

CMD ["python3", "-m", "core.runners.container.entry"]
