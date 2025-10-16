# 多阶段构建 - 第一阶段：构建
FROM python:3.12-alpine as builder

WORKDIR /app

# 安装构建依赖
RUN apk add --no-cache \
    gcc \
    musl-dev

# 创建requirements文件
RUN echo "requests flask flask-cors" > requirements.txt

# 安装Python依赖并清理缓存
RUN pip install --no-cache-dir --user -r requirements.txt && \
    find /root/.cache -type f -delete

# 第二阶段：运行
FROM python:3.12-alpine

WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_DEBUG=0

# 从构建阶段复制已安装的包
COPY --from=builder /root/.local /home/appuser/.local

# 创建非root用户
RUN adduser -D -s /bin/sh appuser && \
    chown -R appuser:appuser /app
USER appuser

# 复制应用代码
COPY --chown=appuser:appuser . .

# 清理不必要的文件
RUN apk del --no-cache gcc musl-dev && \
    rm -rf /var/cache/apk/* && \
    find /home/appuser/.local -name "*.pyc" -delete && \
    find /home/appuser/.local -name "__pycache__" -type d -exec rm -rf {} +

# 暴露端口
EXPOSE 5000

# 设置启动命令
CMD ["python", "main.py"]