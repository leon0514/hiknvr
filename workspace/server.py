import time
import threading
from collections import defaultdict
from typing import Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.responses import JSONResponse
import uvicorn
import hiknvrcap

# =================配置区域=================
NVR_CONFIG = {
    "ip": "172.16.22.16",
    "port": 8000,
    "user": "admin",
    "password": "lww123456"
}


CACHE_TTL = 1
# =========================================

class NVRController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        # 单例模式，确保全局只有一个 Controller
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(NVRController, cls).__new__(cls)
                    cls._instance.init_resources()
        return cls._instance

    def init_resources(self):
        print("[NVR] Initializing SDK Manager...")
        # 假设您的 C++ 模块编译为 hiknvrcap，类名为 HikNvr
        self.nvr = hiknvrcap.HikNvr()
        self.is_connected = False
        
        # 缓存字典: { channel_id: (timestamp, image_bytes) }
        self.image_cache = {}
        
        # 通道锁: { channel_id: Lock() }
        # 作用: 防止同一瞬间多个请求穿透缓存或同时强制刷新
        self.channel_locks = defaultdict(threading.Lock)
        
        self._connect()

    def _connect(self):
        """连接 NVR"""
        if self.is_connected:
            return True
            
        print(f"[NVR] Connecting to {NVR_CONFIG['ip']}...")
        if self.nvr.login(NVR_CONFIG["ip"], NVR_CONFIG["port"], 
                          NVR_CONFIG["user"], NVR_CONFIG["password"]):
            print("[NVR] Connected successfully.")
            self.is_connected = True
            return True
        else:
            print("[NVR] Connection failed!")
            return False

    def _reconnect(self):
        """重连机制"""
        print("[NVR] Connection lost, reconnecting...")
        self.nvr.logout()
        self.is_connected = False
        return self._connect()

    def cleanup(self):
        """资源清理"""
        print("[NVR] Cleaning up...")
        if self.nvr:
            self.nvr.logout()

    def get_channels(self):
        if not self.is_connected:
            if not self._connect():
                return []
        return self.nvr.get_online_channels()

    def get_image(self, channel_id: int, force_iframe: bool = False) -> Optional[bytes]:
        """
        核心逻辑：带锁的缓存读取或强制刷新
        """
        # 1. 获取该通道的专属锁
        # 保证了即使多个请求同时要求强制刷新，也只有一个能执行，其他请求等待后会读取到最新的缓存
        with self.channel_locks[channel_id]:
            current_time = time.time()
            
            if channel_id in self.image_cache:
                ts, data = self.image_cache[channel_id]
                if current_time - ts < CACHE_TTL:
                    return data
            
            # 3. 缓存失效 或 需要强制刷新，执行抓图
            # print(f"[Capture] Channel {channel_id}, Force Refresh: {force_iframe}")
            
            if not self.is_connected:
                if not self._connect():
                    return None

            # ★★★ 新增逻辑：如果需要，先强制生成I帧 ★★★
            if force_iframe:
                if self.nvr.force_iframe(channel_id):
                    # 成功后给予设备短暂的响应时间
                    time.sleep(0.05) 
                else:
                    print(f"[Warning] Failed to force I-Frame for channel {channel_id}.")

            # 调用 C++ 接口 (已释放 GIL，不会阻塞其他 HTTP 线程)
            img_data = self.nvr.capture(channel_id)

            if img_data and len(img_data) > 0:
                # 4. 更新缓存
                self.image_cache[channel_id] = (time.time(), img_data)
                return img_data
            else:
                # 抓图失败尝试重连一次 (应对 session 超时)
                if self._reconnect():
                    # 重连后再次尝试强制I帧和抓图
                    if force_iframe:
                        if self.nvr.force_iframe(channel_id):
                            time.sleep(0.05)
                    
                    img_data = self.nvr.capture(channel_id)
                    if img_data:
                        self.image_cache[channel_id] = (time.time(), img_data)
                        return img_data
                
                return None

# =================FastAPI App=================

# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    controller = NVRController()
    yield
    # 关闭时
    controller.cleanup()

app = FastAPI(title="Hikvision NVR Middleware", lifespan=lifespan)
controller = NVRController()

@app.get("/")
def read_root():
    return {"status": "running", "connected": controller.is_connected}

@app.get("/channels")
def get_channels():
    channels = controller.get_channels()
    return {"count": len(channels), "channels": channels}

@app.get("/capture/{channel_id}")
def capture_image(
    channel_id: int,
    force: bool = Query(False, description="设置为 true 可强制刷新I帧，获取最新的实时图像，会绕过缓存。")
):
    """
    抓取指定通道的图片。
    - 默认使用缓存，性能高。
    - 添加 ?force=true 参数可强制刷新，确保获取最新画面。
    """
    data = controller.get_image(channel_id, force_iframe=force)
    
    if data is None:
        # 返回 503 表示服务端暂时无法获取资源
        raise HTTPException(status_code=503, detail="Capture failed or device offline")
    
    # 直接返回二进制图片，方便浏览器查看或程序调用
    return Response(content=data, media_type="image/jpeg")

if __name__ == "__main__":
    # 启动服务
    uvicorn.run(app, host="0.0.0.0", port=3000)