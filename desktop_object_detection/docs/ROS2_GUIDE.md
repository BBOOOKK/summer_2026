# ROS2 使用指南

## 依赖

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
sudo apt update
sudo apt install python3-colcon-common-extensions ros-$ROS_DISTRO-cv-bridge ros-$ROS_DISTRO-sensor-msgs
```

Ultralytics 与 CUDA PyTorch 需要对 ROS2 使用的 Python 可见。

## 编译

```bash
cd desktop_object_detection/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 模式 A：USB 摄像头

```bash
ros2 run object_detector detector_node --ros-args \
  -p model_path:=$(pwd)/../models/experiment1_1000self_4000public_v1/best.pt \
  -p source_mode:=camera \
  -p camera_id:=0 \
  -p confidence_threshold:=0.5 \
  -p iou_threshold:=0.45 \
  -p imgsz:=640 \
  -p device:=0 \
  -p publish_image:=true \
  -p save_video:=false
```

## 模式 B：订阅图像

```bash
ros2 run object_detector detector_node --ros-args \
  -p model_path:=$(pwd)/../models/experiment1_1000self_4000public_v1/best.pt \
  -p source_mode:=topic \
  -p input_topic:=/camera/image_raw \
  -p device:=0
```

## 输出

- `/object_detection/result`：`std_msgs/msg/String`，JSON 含时间、帧号、FPS、类别、置信度和 bbox。
- `/object_detection/image`：`sensor_msgs/msg/Image`，含检测框、类别、置信度和 FPS。

```bash
ros2 topic echo /object_detection/result
ros2 topic hz /object_detection/result
ros2 topic info /object_detection/image
ros2 run rqt_image_view rqt_image_view /object_detection/image
```

JSON 示例：

```json
{"timestamp":1234567890.0,"frame_id":100,"fps":12.5,"detections":[{"class_id":0,"class_name":"mouse","confidence":0.92,"bbox":{"x1":100.0,"y1":80.0,"x2":260.0,"y2":400.0}}]}
```
