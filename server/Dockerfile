# TLOU Factions revival backend - all servers in one image (pure stdlib Python).
FROM python:3.12-slim
WORKDIR /app/server
COPY . /app/server
# Ports the game connects to (host networking in compose binds these on the host).
EXPOSE 80 7312 7313 7314 7320
CMD ["python3", "run_all.py"]
