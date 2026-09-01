#ifndef ROBOT_GRASP_JOINT__GRASP_JOINT_PLUGIN_HPP_
#define ROBOT_GRASP_JOINT__GRASP_JOINT_PLUGIN_HPP_

#include <gazebo/common/Plugin.hh>

#include <memory>

namespace robot_grasp_joint
{

class GraspJointPluginPrivate;

/// Gazebo Classic plugin which creates a contact-gated detachable fixed joint.
class GraspJointPlugin : public gazebo::ModelPlugin
{
public:
  GraspJointPlugin();
  ~GraspJointPlugin() override;

protected:
  void Load(gazebo::physics::ModelPtr model, sdf::ElementPtr sdf) override;

private:
  std::unique_ptr<GraspJointPluginPrivate> impl_;
};

}  // namespace robot_grasp_joint

#endif  // ROBOT_GRASP_JOINT__GRASP_JOINT_PLUGIN_HPP_
