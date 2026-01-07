#include "hikNvrCap.hpp"
#include <future>
#include <iostream>
#include <fstream>
#include <vector>

void save_image(const std::string& filename, const std::vector<char>& data) {
    std::ofstream ofs(filename, std::ios::binary);
    if (ofs) {
        ofs.write(data.data(), data.size());
    }
}

int main() {
    HikNvrCap nvr;
    
    // 1. 登录
    if (!nvr.Login("192.168.1.64", 8000, "admin", "password123")) {
        return -1;
    }

    // 2. 获取通道
    auto channels = nvr.GetOnlineChannels();
    std::cout << "Online Channels: " << channels.size() << std::endl;

    // 3. 多线程并发抓图 (无延迟核心)
    std::vector<std::future<bool>> futures;
    
    // 为每个线程准备独立的 buffer，避免竞争
    // 注意：在实际高频抓取循环中，这些 buffer 应该被复用，而不是每次循环都销毁
    struct ThreadContext {
        std::vector<char> buffer;
        int channel;
        bool result;
    };
    
    std::vector<ThreadContext> contexts(channels.size());

    auto start_time = std::chrono::steady_clock::now();

    // 启动并发任务
    for (size_t i = 0; i < channels.size(); ++i) {
        contexts[i].channel = channels[i];
        
        // 使用 std::async 启动异步任务
        // launch::async 强制开启新线程
        futures.push_back(std::async(std::launch::async, [&nvr, &ctx = contexts[i]]() {
            // 这里传入 ctx.buffer，每个线程操作自己的内存
            ctx.result = nvr.Capture(ctx.channel, ctx.buffer);
            return ctx.result;
        }));
    }

    // 等待所有任务完成
    for (auto& f : futures) {
        f.get();
    }

    auto end_time = std::chrono::steady_clock::now();
    std::cout << "Captured " << channels.size() << " channels in " 
              << std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count() 
              << " ms." << std::endl;

    // 4. 保存结果 (串行IO，不影响抓图耗时)
    for (const auto& ctx : contexts) {
        if (ctx.result) {
            std::string fname = "chn_" + std::to_string(ctx.channel) + ".jpg";
            save_image(fname, ctx.buffer);
            std::cout << "Saved " << fname << " (" << ctx.buffer.size() / 1024 << " KB)" << std::endl;
        }
    }

    // 析构自动 Logout
    return 0;
}