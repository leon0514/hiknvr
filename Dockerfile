# =================================================================
# Stage 1: Build Environment
# =================================================================
FROM python:3.10-slim AS builder

WORKDIR /app

# ★★★ 新增：修改 APT 镜像源为清华大学源 ★★★
# 备份并替换为新的软件源，以提高国内网络环境下的下载速度
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 1. 安装依赖 (这一层基本不会变)
# 现在会从新的镜像源下载，速度更快
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pybind11

# --- 准备编译环境 ---
COPY ./sdk/hikvision /opt/hikvision

# 2. ★★★ 关键改动 (第一部分) ★★★
# 先只复制 CMakeLists.txt，它决定了项目的结构
COPY ./CMakeLists.txt ./CMakeLists.txt
COPY ./src ./src

RUN cmake -B build -S . \
    -DCMAKE_BUILD_TYPE=Release \
    -Dpybind11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())")


# 5. 运行编译步骤。
# 这一步依赖于源代码。当你修改了 src/ 目录下的任何文件，
# COPY ./src ./src 这一层会失效，从而触发下面的重新编译。
# 但上面的 CMake 配置步骤依然会使用缓存，为你节省时间！
RUN cmake --build build --config Release --parallel


# =================================================================
# Stage 2: Runtime Environment
# =================================================================
FROM python:3.10-slim

WORKDIR /app

# 安装 Python 运行时依赖
RUN pip install --no-cache-dir fastapi uvicorn

# --- 部署编译产物和运行时库 ---

# 1. 从 builder 阶段拷贝编译好的 Python 模块 (.so 文件)
COPY --from=builder /app/build/*.so ./hiknvrcap.so

# 2. 拷贝海康 SDK 的运行时库
COPY --from=builder /opt/hikvision/hik_libs /opt/hikvision/hik_libs

# 3. 配置动态链接器，让系统能找到海康的 .so 文件
RUN echo /opt/hikvision/hik_libs > /etc/ld.so.conf.d/hikvision.conf && ldconfig

# 4. 拷贝 FastAPI 服务脚本
COPY ./workspace/*.py ./

# 暴露 FastAPI 服务端口
EXPOSE 3000

# 启动 FastAPI 应用
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]