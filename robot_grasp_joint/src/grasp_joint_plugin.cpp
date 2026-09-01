#include "robot_grasp_joint/grasp_joint_plugin.hpp"

#include <gazebo/common/Events.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo_ros/node.hpp>
#include <gazebo_msgs/msg/contacts_state.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_srvs/srv/trigger.hpp>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <utility>

namespace robot_grasp_joint
{
namespace
{

using Clock = std::chrono::steady_clock;
using Trigger = std_srvs::srv::Trigger;

template<typename T>
T SdfValue(const sdf::ElementPtr & sdf, const std::string & name, const T & fallback)
{
  if (sdf && sdf->HasElement(name)) {
    return sdf->Get<T>(name);
  }
  return fallback;
}

std::string Lower(std::string value)
{
  std::transform(
    value.begin(), value.end(), value.begin(),
    [](unsigned char character) {return static_cast<char>(std::tolower(character));});
  return value;
}

std::string JsonEscape(const std::string & value)
{
  std::ostringstream stream;
  for (const char character : value) {
    switch (character) {
      case '\\': stream << "\\\\"; break;
      case '"': stream << "\\\""; break;
      case '\n': stream << "\\n"; break;
      case '\r': stream << "\\r"; break;
      case '\t': stream << "\\t"; break;
      default: stream << character; break;
    }
  }
  return stream.str();
}

enum class Command
{
  kAttach,
  kDetach,
};

struct CommandRequest
{
  std::uint64_t id{0};
  Command command{Command::kAttach};
};

struct CommandResult
{
  std::uint64_t id{0};
  bool success{false};
  std::string message;
};

}  // namespace

class GraspJointPluginPrivate
{
public:
  void Load(gazebo::physics::ModelPtr carrier, sdf::ElementPtr sdf)
  {
    carrier_ = std::move(carrier);
    world_ = carrier_->GetWorld();

    robot_model_name_ = SdfValue<std::string>(sdf, "robot_model", "mecharm270");
    parent_link_name_ = SdfValue<std::string>(sdf, "parent_link", "tool0");
    target_model_name_ = SdfValue<std::string>(sdf, "target_model", "target_object");
    target_link_name_ = SdfValue<std::string>(sdf, "target_link", "object");
    joint_name_ = SdfValue<std::string>(sdf, "joint_name", "physical_grasp_joint");
    target_token_ = Lower(
      SdfValue<std::string>(sdf, "target_collision_token", "target_object::"));
    left_token_ = Lower(
      SdfValue<std::string>(sdf, "left_finger_collision_token", "left_finger::"));
    right_token_ = Lower(
      SdfValue<std::string>(sdf, "right_finger_collision_token", "right_finger::"));
    max_attach_distance_ = std::max(
      0.0, SdfValue<double>(sdf, "max_attach_distance", 0.19));
    contact_timeout_ = std::max(
      0.01, SdfValue<double>(sdf, "contact_timeout", 0.35));
    command_timeout_ = std::max(
      0.05, SdfValue<double>(sdf, "command_timeout", 1.0));
    require_bilateral_contact_ = SdfValue<bool>(sdf, "require_bilateral_contact", true);
    auto_attach_ = SdfValue<bool>(sdf, "auto_attach", false);

    const auto attach_service =
      SdfValue<std::string>(sdf, "attach_service", "/grasp/attach");
    const auto detach_service =
      SdfValue<std::string>(sdf, "detach_service", "/grasp/detach");
    const auto status_service =
      SdfValue<std::string>(sdf, "status_service", "/grasp/status");
    const auto contact_topic =
      SdfValue<std::string>(sdf, "contact_topic", "/gazebo/contacts/target");
    const auto state_topic =
      SdfValue<std::string>(sdf, "state_topic", "/grasp/state");

    ros_node_ = gazebo_ros::Node::Get(sdf);
    if (!ros_node_) {
      gzerr << "[robot_grasp_joint] unable to create gazebo_ros node\n";
      return;
    }

    state_publisher_ = ros_node_->create_publisher<std_msgs::msg::String>(state_topic, 10);
    contact_subscription_ = ros_node_->create_subscription<gazebo_msgs::msg::ContactsState>(
      contact_topic,
      rclcpp::QoS(50),
      std::bind(&GraspJointPluginPrivate::OnContacts, this, std::placeholders::_1));
    attach_service_ = ros_node_->create_service<Trigger>(
      attach_service,
      std::bind(
        &GraspJointPluginPrivate::OnAttachService, this,
        std::placeholders::_1, std::placeholders::_2));
    detach_service_ = ros_node_->create_service<Trigger>(
      detach_service,
      std::bind(
        &GraspJointPluginPrivate::OnDetachService, this,
        std::placeholders::_1, std::placeholders::_2));
    status_service_ = ros_node_->create_service<Trigger>(
      status_service,
      std::bind(
        &GraspJointPluginPrivate::OnStatusService, this,
        std::placeholders::_1, std::placeholders::_2));

    update_connection_ = gazebo::event::Events::ConnectWorldUpdateBegin(
      std::bind(&GraspJointPluginPrivate::OnUpdate, this));

    RCLCPP_INFO(
      ros_node_->get_logger(),
      "detachable grasp joint ready: %s::%s -> %s::%s; bilateral_contact=%s",
      robot_model_name_.c_str(), parent_link_name_.c_str(),
      target_model_name_.c_str(), target_link_name_.c_str(),
      require_bilateral_contact_ ? "required" : "disabled");
  }

  ~GraspJointPluginPrivate()
  {
    update_connection_.reset();
    if (joint_) {
      try {
        joint_->Detach();
      } catch (...) {
        // Gazebo may already be tearing down its physics engine.
      }
      joint_.reset();
    }
  }

private:
  void OnContacts(const gazebo_msgs::msg::ContactsState::SharedPtr message)
  {
    bool left = false;
    bool right = false;
    for (const auto & state : message->states) {
      const auto first = Lower(state.collision1_name);
      const auto second = Lower(state.collision2_name);
      std::string other;
      if (first.find(target_token_) != std::string::npos) {
        other = second;
      } else if (second.find(target_token_) != std::string::npos) {
        other = first;
      } else {
        continue;
      }
      left = left || other.find(left_token_) != std::string::npos;
      right = right || other.find(right_token_) != std::string::npos;
    }
    if (!left && !right) {
      return;
    }
    const auto now = Clock::now();
    std::lock_guard<std::mutex> lock(mutex_);
    if (left) {
      last_left_contact_ = now;
      left_contact_seen_ = true;
    }
    if (right) {
      last_right_contact_ = now;
      right_contact_seen_ = true;
    }
  }

  void OnAttachService(
    const std::shared_ptr<Trigger::Request> request,
    std::shared_ptr<Trigger::Response> response)
  {
    (void)request;
    const auto result = Submit(Command::kAttach);
    response->success = result.success;
    response->message = result.message;
  }

  void OnDetachService(
    const std::shared_ptr<Trigger::Request> request,
    std::shared_ptr<Trigger::Response> response)
  {
    (void)request;
    const auto result = Submit(Command::kDetach);
    response->success = result.success;
    response->message = result.message;
  }

  void OnStatusService(
    const std::shared_ptr<Trigger::Request> request,
    std::shared_ptr<Trigger::Response> response)
  {
    (void)request;
    std::lock_guard<std::mutex> lock(mutex_);
    response->success = loaded_entities_.load();
    std::ostringstream message;
    message << "attached=" << (attached_.load() ? "true" : "false")
            << ", entities_ready=" << (loaded_entities_.load() ? "true" : "false")
            << ", bilateral_contact=" << (BilateralContactFreshLocked() ? "true" : "false")
            << ", distance=" << std::fixed << std::setprecision(6) << last_distance_.load()
            << ", attach_count=" << attach_count_.load()
            << ", detach_count=" << detach_count_.load()
            << ", rejected_attach_count=" << rejected_attach_count_.load();
    response->message = message.str();
  }

  CommandResult Submit(Command command)
  {
    std::unique_lock<std::mutex> lock(mutex_);
    if (pending_ || processing_id_ != 0) {
      return CommandResult{0, false, "另一个抓持命令仍在处理"};
    }
    const std::uint64_t id = ++next_command_id_;
    pending_ = std::make_unique<CommandRequest>(CommandRequest{id, command});
    const bool completed = condition_.wait_for(
      lock,
      std::chrono::duration<double>(command_timeout_),
      [this, id]() {return last_result_.id == id;});
    if (completed) {
      return last_result_;
    }
    if (pending_ && pending_->id == id) {
      pending_.reset();
      return CommandResult{id, false, "Gazebo 物理更新未处理命令，命令已取消"};
    }
    const bool finished_after_grace = condition_.wait_for(
      lock,
      std::chrono::milliseconds(250),
      [this, id]() {return last_result_.id == id;});
    if (finished_after_grace) {
      return last_result_;
    }
    return CommandResult{id, false, "抓持命令执行超时；请查询 /grasp/status"};
  }

  bool ResolveEntities(std::string & message)
  {
    if (!world_) {
      message = "Gazebo world 不可用";
      return false;
    }
    robot_model_ = world_->ModelByName(robot_model_name_);
    target_model_ = world_->ModelByName(target_model_name_);
    if (!robot_model_ || !target_model_) {
      message = "等待模型：" + robot_model_name_ + " / " + target_model_name_;
      return false;
    }
    parent_link_ = robot_model_->GetLink(parent_link_name_);
    target_link_ = target_model_->GetLink(target_link_name_);
    if (!parent_link_ || !target_link_) {
      message = "找不到链接：" + parent_link_name_ + " / " + target_link_name_;
      return false;
    }
    message = "模型和链接已就绪";
    return true;
  }

  bool BilateralContactFreshLocked() const
  {
    if (!left_contact_seen_ || !right_contact_seen_) {
      return false;
    }
    const auto now = Clock::now();
    const auto timeout = std::chrono::duration<double>(contact_timeout_);
    return now - last_left_contact_ <= timeout && now - last_right_contact_ <= timeout;
  }

  CommandResult Execute(const CommandRequest & request)
  {
    if (request.command == Command::kDetach) {
      return Detach(request.id);
    }
    return Attach(request.id);
  }

  CommandResult Attach(std::uint64_t id)
  {
    if (attached_.load() && joint_) {
      return CommandResult{id, true, "抓持固定关节已经处于附着状态"};
    }
    std::string resolve_message;
    if (!ResolveEntities(resolve_message)) {
      ++rejected_attach_count_;
      return CommandResult{id, false, resolve_message};
    }

    const auto parent_position = parent_link_->WorldPose().Pos();
    const auto target_position = target_link_->WorldPose().Pos();
    last_distance_.store(parent_position.Distance(target_position));
    if (last_distance_.load() > max_attach_distance_) {
      ++rejected_attach_count_;
      std::ostringstream message;
      message << "目标物距离 " << std::fixed << std::setprecision(4) << last_distance_.load()
              << " m，超过附着阈值 " << max_attach_distance_ << " m"
              << "；tool=(" << parent_position.X() << "," << parent_position.Y()
              << "," << parent_position.Z() << ") target=(" << target_position.X()
              << "," << target_position.Y() << "," << target_position.Z() << ")";
      return CommandResult{id, false, message.str()};
    }

    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (require_bilateral_contact_ && !BilateralContactFreshLocked()) {
        ++rejected_attach_count_;
        return CommandResult{id, false, "未检测到左右指尖与目标物的近期双侧接触"};
      }
    }

    try {
      const auto stale_joint = robot_model_->GetJoint(joint_name_);
      if (stale_joint) {
        stale_joint->Detach();
        robot_model_->RemoveJoint(joint_name_);
      }
      joint_ = robot_model_->CreateJoint(
        joint_name_, "fixed", parent_link_, target_link_);
      if (!joint_) {
        ++rejected_attach_count_;
        return CommandResult{id, false, "Gazebo 未能创建 fixed joint"};
      }
      joint_->Init();
      attached_.store(true);
      ++attach_count_;
      return CommandResult{id, true, "物理 fixed joint 已附着"};
    } catch (const std::exception & error) {
      joint_.reset();
      attached_.store(false);
      ++rejected_attach_count_;
      return CommandResult{id, false, std::string("创建 fixed joint 异常：") + error.what()};
    }
  }

  CommandResult Detach(std::uint64_t id)
  {
    if (!joint_ || !attached_.load()) {
      attached_.store(false);
      return CommandResult{id, true, "抓持固定关节已经处于分离状态"};
    }
    try {
      joint_->Detach();
      if (robot_model_) {
        robot_model_->RemoveJoint(joint_name_);
      }
      joint_.reset();
      attached_.store(false);
      // ODE may leave a body asleep after detaching it from a static or
      // world-anchored parent.  Explicitly wake the payload so gravity and
      // the opening fingers take effect immediately after release.
      if (target_model_ && target_link_) {
        target_model_->SetAutoDisable(false);
        target_model_->SetEnabled(true);
        target_link_->SetAutoDisable(false);
        target_link_->SetGravityMode(true);
        target_link_->SetEnabled(true);
        auto velocity = target_link_->WorldLinearVel();
        velocity.Z() -= 1.0e-6;
        target_link_->SetLinearVel(velocity);
      }
      ++detach_count_;
      return CommandResult{id, true, "物理 fixed joint 已拆除"};
    } catch (const std::exception & error) {
      return CommandResult{id, false, std::string("拆除 fixed joint 异常：") + error.what()};
    }
  }

  void PublishState(const CommandResult & result)
  {
    if (!state_publisher_) {
      return;
    }
    std_msgs::msg::String message;
    std::ostringstream payload;
    payload << "{\"attached\":" << (attached_.load() ? "true" : "false")
            << ",\"success\":" << (result.success ? "true" : "false")
            << ",\"message\":\"" << JsonEscape(result.message) << "\""
            << ",\"attach_count\":" << attach_count_.load()
            << ",\"detach_count\":" << detach_count_.load()
            << ",\"rejected_attach_count\":" << rejected_attach_count_.load() << "}";
    message.data = payload.str();
    state_publisher_->publish(message);
  }

  void OnUpdate()
  {
    std::string resolve_message;
    const bool resolved = ResolveEntities(resolve_message);
    double distance = last_distance_.load();
    if (resolved) {
      distance = parent_link_->WorldPose().Pos().Distance(target_link_->WorldPose().Pos());
    }

    std::unique_ptr<CommandRequest> request;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      loaded_entities_.store(resolved);
      last_distance_.store(distance);
      if (auto_attach_ && !auto_attach_submitted_) {
        auto_attach_submitted_ = true;
        pending_ = std::make_unique<CommandRequest>(
          CommandRequest{++next_command_id_, Command::kAttach});
      }
      if (pending_) {
        processing_id_ = pending_->id;
        request = std::move(pending_);
      }
    }
    if (!request) {
      return;
    }

    const auto result = Execute(*request);
    {
      std::lock_guard<std::mutex> lock(mutex_);
      processing_id_ = 0;
      last_result_ = result;
    }
    condition_.notify_all();
    PublishState(result);
    if (result.success) {
      RCLCPP_INFO(ros_node_->get_logger(), "%s", result.message.c_str());
    } else {
      RCLCPP_WARN(ros_node_->get_logger(), "%s", result.message.c_str());
    }
  }

  gazebo::physics::ModelPtr carrier_;
  gazebo::physics::WorldPtr world_;
  gazebo::physics::ModelPtr robot_model_;
  gazebo::physics::ModelPtr target_model_;
  gazebo::physics::LinkPtr parent_link_;
  gazebo::physics::LinkPtr target_link_;
  gazebo::physics::JointPtr joint_;
  gazebo::event::ConnectionPtr update_connection_;

  gazebo_ros::Node::SharedPtr ros_node_;
  rclcpp::Subscription<gazebo_msgs::msg::ContactsState>::SharedPtr contact_subscription_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr state_publisher_;
  rclcpp::Service<Trigger>::SharedPtr attach_service_;
  rclcpp::Service<Trigger>::SharedPtr detach_service_;
  rclcpp::Service<Trigger>::SharedPtr status_service_;

  std::string robot_model_name_;
  std::string parent_link_name_;
  std::string target_model_name_;
  std::string target_link_name_;
  std::string joint_name_;
  std::string target_token_;
  std::string left_token_;
  std::string right_token_;
  double max_attach_distance_{0.19};
  double contact_timeout_{0.35};
  double command_timeout_{1.0};
  bool require_bilateral_contact_{true};
  bool auto_attach_{false};

  mutable std::mutex mutex_;
  std::condition_variable condition_;
  std::unique_ptr<CommandRequest> pending_;
  std::uint64_t processing_id_{0};
  std::uint64_t next_command_id_{0};
  CommandResult last_result_;
  Clock::time_point last_left_contact_{};
  Clock::time_point last_right_contact_{};
  bool left_contact_seen_{false};
  bool right_contact_seen_{false};
  std::atomic<bool> loaded_entities_{false};
  std::atomic<bool> attached_{false};
  bool auto_attach_submitted_{false};
  std::atomic<double> last_distance_{0.0};
  std::atomic<std::uint64_t> attach_count_{0};
  std::atomic<std::uint64_t> detach_count_{0};
  std::atomic<std::uint64_t> rejected_attach_count_{0};
};

GraspJointPlugin::GraspJointPlugin()
: impl_(std::make_unique<GraspJointPluginPrivate>())
{
}

GraspJointPlugin::~GraspJointPlugin() = default;

void GraspJointPlugin::Load(gazebo::physics::ModelPtr model, sdf::ElementPtr sdf)
{
  impl_->Load(std::move(model), std::move(sdf));
}

GZ_REGISTER_MODEL_PLUGIN(GraspJointPlugin)

}  // namespace robot_grasp_joint
