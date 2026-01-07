#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "hikNvrCap.hpp" // 包含上一轮优化的头文件

namespace py = pybind11;

PYBIND11_MODULE(hiknvrcap, m) {
    py::class_<HikNvrCap>(m, "HikNvr")
        .def(py::init<>())
        .def("login", &HikNvrCap::Login)
        .def("logout", &HikNvrCap::Logout)
        .def("get_online_channels", &HikNvrCap::GetOnlineChannels)
        .def("is_connected", &HikNvrCap::IsConnected)
        .def("force_iframe", 
            [](HikNvrCap& self, int channel, int stream_type) {
                return self.ForceIFrame(channel, stream_type);
            }, "Force I-Frame on specified channel and stream type", py::arg("channel"), py::arg("stream_type") = 0)
        .def("capture", 
            [](HikNvrCap& self, int channel) {
                std::vector<char> buffer;
                bool success = false;
                {
                    py::gil_scoped_release release;
                    success = self.Capture(channel, buffer);
                }

                if (!success) {
                    return py::bytes(""); // 失败返回空字节
                }
                return py::bytes(buffer.data(), buffer.size());
            }, "Capture image from channel. Releases GIL during network I/O.", 
            py::arg("channel"));
}