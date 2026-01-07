import hiknvrcap
import time
import os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading

# 配置信息
NVR_IP = "172.16.22.16"
NVR_PORT = 8000
NVR_USER = "admin"
NVR_PWD = "lww123456"
SAVE_DIR = "./snapshots" 

def save_image(data, filename):
    """辅助函数：保存图片到磁盘"""
    if data:
        with open(filename, 'wb') as f:
            f.write(data)
        return len(data)
    return 0


def run_multithreaded():
    print("-" * 30)
    print("[Thread Mode] Starting...")
    
    # 1. 主线程初始化并登录
    nvr = hiknvrcap.HikNvr()
    if not nvr.login(NVR_IP, NVR_PORT, NVR_USER, NVR_PWD):
        print("Login failed")
        return

    channels = nvr.get_online_channels()
    print(f"Online Channels: {channels}")

    if not channels:
        return

    # 2. 定义线程任务函数
    def task_capture(ch):
        # 记录时间
        t_start = time.time()
        # 调用 C++ 接口 (内部已释放 GIL，真正并行)
        img_bytes = nvr.capture(ch) 
        t_cost = (time.time() - t_start) * 1000
        
        if img_bytes:
            # 模拟保存
            fname = f"thread_ch{ch}.jpg"
            size = save_image(img_bytes, fname)
            return f"CH{ch}: OK ({size/1024:.1f}KB) in {t_cost:.1f}ms"
        else:
            return f"CH{ch}: FAIL"

    # 3. 使用线程池并发抓取
    start_total = time.time()
    
    # max_workers 建议设置为通道数，或者 CPU 核心数 * 2
    with ThreadPoolExecutor(max_workers=len(channels)) as executor:
        results = list(executor.map(task_capture, channels))

    end_total = time.time()
    
    for res in results:
        print(res)
        
    print(f"[Thread Mode] Total time: {(end_total - start_total)*1000:.1f} ms")
    
    # 显式登出（也可依赖析构函数）
    nvr.logout()

# ==========================================
# 模式二：多进程抓取
# 适用场景：抓图后需要进行极高负载的 CPU 计算 (如 AI 检测)
# 注意：SDK 句柄不可跨进程，每个进程需独立登录
# ==========================================

# 全局变量，用于在子进程中保持连接
process_nvr_instance = None

def init_process():
    """进程初始化函数：每个子进程启动时调用一次"""
    global process_nvr_instance
    print(f"[Process {os.getpid()}] Initializing SDK...")
    process_nvr_instance = hiknvrcap.HikNvr()
    # 每个进程独立登录
    if not process_nvr_instance.login(NVR_IP, NVR_PORT, NVR_USER, NVR_PWD):
        print(f"[Process {os.getpid()}] Login failed!")

def process_task(channel):
    """进程任务函数"""
    global process_nvr_instance
    if not process_nvr_instance or not process_nvr_instance.is_connected():
        return f"CH{channel}: Process not logged in"
    
    t_start = time.time()
    img_bytes = process_nvr_instance.capture(channel)
    t_cost = (time.time() - t_start) * 1000
    
    if img_bytes:
        fname = f"process_ch{channel}.jpg"
        size = save_image(img_bytes, fname)
        return f"[PID {os.getpid()}] CH{channel}: OK ({size/1024:.1f}KB) in {t_cost:.1f}ms"
    return f"[PID {os.getpid()}] CH{channel}: FAIL"

def run_multiprocess():
    print("-" * 30)
    print("[Process Mode] Starting...")
    
    # 主进程先获取通道列表（只需登录一次获取列表）
    temp_nvr = hiknvrcap.HikNvr()
    if not temp_nvr.login(NVR_IP, NVR_PORT, NVR_USER, NVR_PWD):
        return
    channels = temp_nvr.get_online_channels()
    temp_nvr.logout() # 获取完列表就登出
    del temp_nvr
    
    print(f"Target Channels: {channels}")

    start_total = time.time()

    # 启动进程池
    # initializer=init_process 保证每个进程只登录一次，而不是每次抓图都登录
    with ProcessPoolExecutor(max_workers=4, initializer=init_process) as executor:
        results = list(executor.map(process_task, channels))

    end_total = time.time()

    for res in results:
        print(res)
    
    print(f"[Process Mode] Total time: {(end_total - start_total)*1000:.1f} ms")

if __name__ == "__main__":
    # 确保海康 SDK 库路径在环境变量中，或者将库文件拷贝到当前目录
    
    # 1. 运行多线程模式 (SDK 抓图首选)
    run_multithreaded()
    
    # 2. 运行多进程模式 (计算密集型首选)
    # run_multiprocess()