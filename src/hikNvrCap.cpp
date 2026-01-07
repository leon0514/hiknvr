#include "hikNvrCap.hpp"
#include <iostream>
#include <cstring>
#include <thread>

// -----------------------------------------------------------
// SDK Manager 实现
// -----------------------------------------------------------
HikSDKManager& HikSDKManager::Instance() {
    static HikSDKManager instance;
    return instance;
}

HikSDKManager::HikSDKManager() : initialized_(false) {
    // SDK初始化
    if (NET_DVR_Init()) {
        initialized_ = true;
        // 设置连接超时时间 (毫秒)
        NET_DVR_SetConnectTime(2000, 1);
        // 设置重连机制 (间隔毫秒, 是否启用)
        NET_DVR_SetReconnect(10000, true);
        // 可选：设置日志
        // NET_DVR_SetLogToFile(3, "./sdkLog", false);
        std::cout << "[HikSDK] Initialized successfully." << std::endl;
    } else {
        std::cerr << "[HikSDK] Init failed. Err: " << NET_DVR_GetLastError() << std::endl;
    }
}

HikSDKManager::~HikSDKManager() {
    if (initialized_) {
        NET_DVR_Cleanup();
        std::cout << "[HikSDK] Cleanup." << std::endl;
    }
}

// -----------------------------------------------------------
// HikNvrCap 实现
// -----------------------------------------------------------
HikNvrCap::HikNvrCap() : lUserID_(-1) {
    // 构造时确保 SDK 已初始化
    HikSDKManager::Instance();
}

HikNvrCap::~HikNvrCap() {
    Logout();
}

bool HikNvrCap::Login(const std::string& ip, int port, const std::string& user, const std::string& pwd) {
    if (lUserID_ >= 0) Logout();

    if (!HikSDKManager::Instance().IsInitialized()) {
        std::cerr << "[HikNvrCap] SDK not initialized." << std::endl;
        return false;
    }

    NET_DVR_USER_LOGIN_INFO struLoginInfo = {0};
    NET_DVR_DEVICEINFO_V40 struDeviceInfoV40 = {0};

    struLoginInfo.bUseAsynLogin = 0; // 同步登录
    strncpy(struLoginInfo.sDeviceAddress, ip.c_str(), NET_DVR_DEV_ADDRESS_MAX_LEN - 1);
    struLoginInfo.wPort = port;
    strncpy(struLoginInfo.sUserName, user.c_str(), NAME_LEN - 1);
    strncpy(struLoginInfo.sPassword, pwd.c_str(), NAME_LEN - 1);

    lUserID_ = NET_DVR_Login_V40(&struLoginInfo, &struDeviceInfoV40);

    if (lUserID_ < 0) {
        std::cerr << "[HikNvrCap] Login failed (" << ip << "). Err: " << NET_DVR_GetLastError() << std::endl;
        return false;
    }

    std::cout << "[HikNvrCap] Login success. Device ID: " << lUserID_ << std::endl;
    return true;
}

void HikNvrCap::Logout() {
    if (lUserID_ >= 0) {
        if (!NET_DVR_Logout(lUserID_)) {
             std::cerr << "[HikNvrCap] Logout warning. Err: " << NET_DVR_GetLastError() << std::endl;
        }
        lUserID_ = -1;
    }
}

std::vector<int> HikNvrCap::GetOnlineChannels() const {
    std::vector<int> channels;
    if (lUserID_ < 0) return channels;

    NET_DVR_IPPARACFG_V40 struIPAccessCfgV40 = {0};
    DWORD dwReturned = 0;

    // 获取IP通道资源配置
    if (!NET_DVR_GetDVRConfig(lUserID_, NET_DVR_GET_IPPARACFG_V40, 0, &struIPAccessCfgV40, sizeof(struIPAccessCfgV40), &dwReturned)) {
        std::cerr << "[HikNvrCap] Get IP Config failed. Err: " << NET_DVR_GetLastError() << std::endl;
        return channels;
    }

    // 遍历64个IP通道
    for (DWORD i = 0; i < struIPAccessCfgV40.dwDChanNum; i++) {
        // byEnable: 1-启用
        if (struIPAccessCfgV40.struStreamMode[i].uGetStream.struChanInfo.byEnable == 1) {
            // 起始数字通道号 + 索引
            int iChannelID = i + struIPAccessCfgV40.dwStartDChan;
            channels.push_back(iChannelID);
        }
    }
    return channels;
}

bool HikNvrCap::ForceIFrame(int channel, int stream_type) const {
    if (!IsConnected()) {
        return false;
    }

    BOOL result = FALSE;
    if (stream_type == 0) { // 主码流
        result = NET_DVR_MakeKeyFrame(lUserID_, channel);
    } else { // 子码流
        result = NET_DVR_MakeKeyFrameSub(lUserID_, channel);
    }

    if (!result) {
        return false;
    }

    return true;
}


bool HikNvrCap::Capture(int channel, std::vector<char>& out_buffer) const {
    if (lUserID_ < 0) return false;

    NET_DVR_JPEGPARA strPicPara = {0};
    strPicPara.wPicQuality = 0; // 0-最好
    strPicPara.wPicSize = 0xff; // 0xff-Auto

    DWORD dwReturnedSize = 0;
    
    const size_t INITIAL_SIZE = 1024 * 1024; // 1MB
    if (out_buffer.size() < INITIAL_SIZE) {
        out_buffer.resize(INITIAL_SIZE); 
    }

    // 第一次尝试抓取
    // 注意：data() 返回指针，size() 是当前缓冲区大小
    BOOL bRet = NET_DVR_CaptureJPEGPicture_NEW(
        lUserID_, 
        channel, 
        &strPicPara, 
        out_buffer.data(), 
        static_cast<DWORD>(out_buffer.size()), 
        &dwReturnedSize
    );

    // 检查是否缓冲区过小 (SDK错误号 43: NET_DVR_BUFFER_OVERFLOW)
    // 某些旧版SDK可能不返回需要的 dwReturnedSize，这里做防御性扩容
    while (!bRet && NET_DVR_GetLastError() == NET_DVR_NOENOUGH_BUF) {
        size_t new_size = (dwReturnedSize > out_buffer.size()) ? dwReturnedSize : (out_buffer.size() * 2); // 最小扩到2MB
        out_buffer.resize(new_size);

        // 重试
        bRet = NET_DVR_CaptureJPEGPicture_NEW(
            lUserID_, 
            channel, 
            &strPicPara, 
            out_buffer.data(), 
            static_cast<DWORD>(out_buffer.size()), 
            &dwReturnedSize
        );
    }

    if (!bRet) {
        // 抓取失败，建议打印日志但不一定抛出异常
        std::cerr << "Capture failed Ch" << channel << " Err:" << NET_DVR_GetLastError() << std::endl;
        return false;
    }

    // 成功：调整 vector 的逻辑大小为实际图片大小
    // 这一步非常重要，否则 vector.size() 还是分配的大小，保存文件会多出垃圾数据
    out_buffer.resize(dwReturnedSize);
    
    return true;
}