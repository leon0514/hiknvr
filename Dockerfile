# =================================================================
# Stage 1: Build Environment
# =================================================================
FROM python:3.10-slim AS builder

WORKDIR /app

# 安装编译所需的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# 安装 pybind11 作为编译时依赖
RUN pip install --no-cache-dir pybind11

# --- 准备编译环境 ---

# 拷贝海康 SDK 到镜像中的标准位置
COPY ./sdk/hikvision /opt/hikvision

# 拷贝 C++ 源代码和 CMakeLists.txt
COPY ./src ./src
COPY ./CMakeLists.txt ./CMakeLists.txt

# --- 执行 CMake 编译 ---

# 1. 配置项目 (在 build 目录下)
#    ★★★ 关键修改 ★★★
#    我们使用 python -c '...' 来执行一小段 Python 代码，
#    调用 pybind11.get_cmake_dir() 来获取其 CMake 配置文件的路径，
#    然后通过 -Dpybind11_DIR=... 将这个路径传递给 CMake。
RUN cmake -B build -S . \
    -DCMAKE_BUILD_TYPE=Release \
    -Dpybind11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())")

# 2. 编译项目 ( --parallel 使用所有可用核心加速编译 )
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
COPY ./workspace/* ./

# 暴露 FastAPI 服务端口
EXPOSE 3000

# 启动 FastAPI 应用
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]