FROM espressif/idf:release-v5.3

SHELL ["/bin/bash", "-lc"]
WORKDIR /workspace

# Install Python deps inside ESP-IDF managed environment (includes pip)
RUN source /opt/esp/idf/export.sh >/dev/null 2>&1 \
 && python -m pip install --no-cache-dir -U pip \
 && python -m pip install --no-cache-dir \
      numpy pyserial fastapi "uvicorn[standard]" requests python-multipart

# Copy repo into image
COPY . /workspace

# Copy entrypoint outside /workspace so it keeps working even if /workspace is bind-mounted from a noexec filesystem.
RUN install -m 0755 /workspace/docker/entrypoint.sh /usr/local/bin/edgeflow-entrypoint.sh \
 && sed -i 's/\r$//' /usr/local/bin/edgeflow-entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/bin/bash","-lc","/usr/local/bin/edgeflow-entrypoint.sh"]
