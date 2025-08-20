# ---- Base Stage ----
FROM python:3.10-slim

# 设置环境变量，有助于 Python 在容器化环境中的表现
ENV PYTHONDONTWRITEBYTECODE 1  # 防止 python 生成 .pyc 文件
ENV PYTHONUNBUFFERED 1         # 确保 Python 输出直接发送到终端，便于日志查看

# 设置工作目录
WORKDIR /app

# 1. 创建一个非 root 用户和用户组
#    -D: 不要为用户设置密码
#    -S: 创建一个系统用户
RUN addgroup --system app && adduser --system --group app

# 2. 复制依赖文件并安装
#    先只复制依赖相关文件，以充分利用缓存
COPY ./requirements.txt ./VERSION /app/
RUN pip install --no-cache-dir -r requirements.txt

# 3. 将工作目录的所有权交给新创建的用户
#    注意：这里我们暂时还需要 root 权限来复制和修改文件权限
#    所以先不要切换用户
COPY . .

# 将整个 /app 目录的所有权赋给 app 用户
# 确保应用有权限读写其需要的文件
RUN chown -R app:app /app

# 4. 切换到新创建的非 root 用户
USER app

# 暴露端口
EXPOSE 8000

# 运行应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
