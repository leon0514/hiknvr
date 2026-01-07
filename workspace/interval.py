import hiknvrcap
import time
import hashlib
import statistics

# ================= 配置 =================
IP = "172.16.22.16"
PORT = 8000
USER = "admin"
PWD = "lww123456"
CHANNEL = 33        # 要测试的通道号
TEST_DURATION = 10  # 测试持续时间 (秒)
# ========================================

def get_image_fingerprint(data):
    """
    计算图片指纹。
    为了速度，先比较长度，长度一样再比较哈希。
    """
    if not data:
        return None
    # MD5 足够快，且能区分微小差异
    return hashlib.md5(data).hexdigest()

def main():
    print(f"Initializing SDK...")
    nvr = hiknvrcap.HikNvr()
    
    if not nvr.login(IP, PORT, USER, PWD):
        print("Login failed!")
        return

    print(f"Connected. Starting stress test on Channel {CHANNEL} for {TEST_DURATION} seconds...")
    print("Capturing as fast as possible...")

    # 数据记录
    # 格式: (timestamp, is_different_from_previous, size_bytes)
    capture_logs = []
    
    start_time = time.time()
    last_fingerprint = None
    
    count_request = 0
    count_unique = 0
    
    try:
        while time.time() - start_time < TEST_DURATION:
            t_req = time.time()
            
            # 执行抓图
            if nvr.force_iframe(CHANNEL):
                time.sleep(0.05)
            img_data = nvr.capture(CHANNEL)
            count_request += 1
            
            if not img_data:
                continue
                
            # 计算指纹
            curr_fingerprint = get_image_fingerprint(img_data)
            
            # 判断是否与上一张不同
            is_different = False
            if curr_fingerprint != last_fingerprint:
                is_different = True
                last_fingerprint = curr_fingerprint
                count_unique += 1
            
            capture_logs.append({
                "time": t_req,
                "diff": is_different,
                "size": len(img_data)
            })
            
    except KeyboardInterrupt:
        print("Test interrupted.")
    finally:
        nvr.logout()

    # ================= 数据分析 =================
    if not capture_logs:
        print("No data captured.")
        return

    duration = capture_logs[-1]["time"] - capture_logs[0]["time"]
    
    # 1. 提取所有“不同图片”的时间点
    unique_timestamps = [log["time"] for log in capture_logs if log["diff"]]
    
    # 2. 计算不同图片之间的时间差 (Intervals)
    intervals = []
    for i in range(1, len(unique_timestamps)):
        diff = unique_timestamps[i] - unique_timestamps[i-1]
        intervals.append(diff)
        
    print("\n" + "="*40)
    print("           TEST RESULTS           ")
    print("="*40)
    print(f"Total Duration    : {duration:.2f} s")
    print(f"Total Requests    : {count_request}")
    print(f"Unique Images     : {len(unique_timestamps)}")
    print(f"Request FPS       : {count_request / duration:.1f} req/s (Script capability)")
    print(f"Effective FPS     : {len(unique_timestamps) / duration:.1f} fps (Camera capability)")
    print("-" * 40)
    
    if intervals:
        min_int = min(intervals) * 1000
        max_int = max(intervals) * 1000
        avg_int = statistics.mean(intervals) * 1000
        
        print(f"MIN Interval      : {min_int:.2f} ms")
        print(f"MAX Interval      : {max_int:.2f} ms")
        print(f"AVG Interval      : {avg_int:.2f} ms")
        print("-" * 40)
        
        print(f"Recommended Limit : {avg_int * 1.1:.0f} ms (Avg + 10% buffer)")
        print("Conclusion:")
        if avg_int < 45: 
            print("  -> Camera is likely 25 FPS (Frame update every 40ms)")
        elif avg_int < 25:
            print("  -> Camera is likely 60 FPS")
        elif avg_int > 1000:
            print("  -> Very slow updates (check network or camera settings)")
        
        print(f"\nTo ensure different images, wait at least: {max_int:.0f} ms")
    else:
        print("Could not calculate intervals (not enough unique images).")

if __name__ == "__main__":
    main()