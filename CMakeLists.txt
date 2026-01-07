# CMake 最低版本要求
cmake_minimum_required(VERSION 3.15)

# 项目名称和语言
project(hiknvrcap LANGUAGES CXX)

# 设置 C++ 标准为 C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- 寻找依赖 ---
find_package(pybind11 REQUIRED)
find_package(Python 3.10 REQUIRED COMPONENTS Interpreter Development)

# --- 定义海康 SDK 路径 (在 Dockerfile 中固定) ---
set(HIK_SDK_ROOT /opt/hikvision)
set(HIK_INCLUDE_DIR ${HIK_SDK_ROOT}/hik_header)
set(HIK_LIBRARY_DIR ${HIK_SDK_ROOT}/hik_libs)

# --- 自动发现源文件 ---
# 这会将 src 目录下的所有 .cpp 文件 (hikNvrCap.cpp, interface.cpp) 
# 添加到变量 SRC_FILES 中。
aux_source_directory(src SRC_FILES)

# --- 创建 Python 模块 ---
# 使用 pybind11_add_module 创建名为 "hiknvrcap" 的共享库 (.so)
# 将自动发现的源文件列表传递给它
pybind11_add_module(hiknvrcap SHARED ${SRC_FILES})

# --- 链接依赖 ---

# 1. 为模块添加海康的头文件搜索路径
#    ★★★ 关键修正 ★★★
#    这里使用 PUBLIC 关键字，确保任何依赖于此目标的其他目标也能看到这个头文件路径。
#    虽然在这里不是必须的，但这是一个好的实践。
target_include_directories(hiknvrcap PUBLIC
    ${HIK_INCLUDE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/src  # 同时把 src 目录也加进去，方便头文件相互引用
)

# 2. 为模块添加海康的库文件搜索路径
target_link_directories(hiknvrcap PRIVATE ${HIK_LIBRARY_DIR})

# 3. 链接海康 SDK 库和其他系统库
target_link_libraries(hiknvrcap PRIVATE hcnetsdk dl)

# (可选) 设置 Release 模式下的优化级别
set_target_properties(hiknvrcap PROPERTIES
    COMPILE_FLAGS_RELEASE "-O2 -DNDEBUG"
)