// Geometric controller for MIT VNAV Lab 3 (VNAV2021 interface).
// Fix: altitude integral + optional vertical position gain to remove sustained height bias.
#include <ros/ros.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.h>
#include <tf2/utils.h>
#include <mav_msgs/Actuators.h>
#include <nav_msgs/Odometry.h>
#include <trajectory_msgs/MultiDOFJointTrajectoryPoint.h>
#include <Eigen/Dense>
#include <cmath>

class Controller {
  ros::NodeHandle nh_, pnh_{"~"};
  ros::Subscriber desired_sub_, state_sub_;
  ros::Publisher rotor_pub_;
  ros::Timer timer_;
  Eigen::Vector3d x_=Eigen::Vector3d::Zero(), v_=x_, omega_=x_, xd_=x_, vd_=x_, ad_=x_;
  Eigen::Matrix3d R_=Eigen::Matrix3d::Identity(), J_=R_;
  Eigen::Matrix4d inverse_allocation_;
  double yaw_=0, kx_=4, kv_=4, kz_=-1, kr_=100, kw_=20, hz_=200, drag_scale_=0, ki_z_=0, iz_=0, iz_lim_=3.0;
  ros::Time last_t_;
  bool have_state_=false, have_desired_=false, have_time_=false;
  static Eigen::Vector3d vec(const geometry_msgs::Vector3& v) { return {v.x,v.y,v.z}; }
 public:
  Controller() {
    nh_.param("kx",kx_,4.0); nh_.param("kv",kv_,4.0);
    nh_.param("kz",kz_,-1.0); // if <0, use kx
    nh_.param("kr",kr_,100.0); nh_.param("komega",kw_,20.0);
    nh_.param("ki_z",ki_z_,0.0);
    pnh_.param("frequency",hz_,200.0); pnh_.param("drag_compensation",drag_scale_,0.0);
    if(kz_<0) kz_=kx_;
    J_.diagonal() << .1,.2,.1;
    const double cf=1e-3, cd=1e-5, a=cf*.3/std::sqrt(2.0);
    Eigen::Matrix4d allocation;
    allocation << cf,cf,cf,cf, a,a,-a,-a, -a,a,a,-a, cd,-cd,cd,-cd;
    inverse_allocation_=allocation.inverse();
    desired_sub_=nh_.subscribe("desired_state",1,&Controller::desired,this);
    state_sub_=nh_.subscribe("current_state",1,&Controller::state,this,ros::TransportHints().tcpNoDelay());
    rotor_pub_=nh_.advertise<mav_msgs::Actuators>("rotor_speed_cmds",1);
    timer_=nh_.createTimer(ros::Duration(1.0/hz_),&Controller::step,this);
    ROS_INFO("Geometric control: kx=%.2f kz=%.2f kv=%.2f ki_z=%.2f kR=%.2f kOmega=%.2f, %.0f Hz",
             kx_,kz_,kv_,ki_z_,kr_,kw_,hz_);
  }
  void desired(const trajectory_msgs::MultiDOFJointTrajectoryPoint& msg) {
    if(msg.transforms.empty()||msg.velocities.empty()||msg.accelerations.empty()) return;
    xd_=vec(msg.transforms[0].translation); vd_=vec(msg.velocities[0].linear);
    ad_=vec(msg.accelerations[0].linear); yaw_=tf2::getYaw(msg.transforms[0].rotation);
    have_desired_=xd_.allFinite()&&vd_.allFinite()&&ad_.allFinite()&&std::isfinite(yaw_);
  }
  void state(const nav_msgs::Odometry& msg) {
    const auto& q=msg.pose.pose.orientation;
    Eigen::Quaterniond quat(q.w,q.x,q.y,q.z);
    if(!quat.coeffs().allFinite()||quat.norm()<1e-9) return;
    R_=quat.normalized().toRotationMatrix();
    x_ << msg.pose.pose.position.x,msg.pose.pose.position.y,msg.pose.pose.position.z;
    v_=vec(msg.twist.twist.linear);
    omega_=R_.transpose()*vec(msg.twist.twist.angular);
    have_state_=x_.allFinite()&&v_.allFinite()&&omega_.allFinite();
  }
  void step(const ros::TimerEvent&) {
    if(!have_state_||!have_desired_) return;
    const ros::Time now=ros::Time::now();
    double dt=0.005;
    if(have_time_) dt=std::max(1e-4,(now-last_t_).toSec());
    last_t_=now; have_time_=true;
    const double ez=xd_.z()-x_.z();
    iz_=std::max(-iz_lim_,std::min(iz_lim_,iz_+ez*dt));
    const Eigen::Vector3d vb=R_.transpose()*v_;
    const Eigen::Vector3d drag_body=-drag_scale_*Eigen::Vector3d(.1,.1,.2).cwiseProduct(vb.cwiseProduct(vb.cwiseAbs()));
    Eigen::Vector3d kx_vec(kx_,kx_,kz_);
    Eigen::Vector3d A=-kx_vec.cwiseProduct(x_-xd_)-kv_*(v_-vd_)+Eigen::Vector3d(0,0,9.81)+ad_-R_*drag_body;
    A.z()+=ki_z_*iz_;
    if(A.norm()<1e-9) return;
    const Eigen::Vector3d b3=A.normalized(), heading(std::cos(yaw_),std::sin(yaw_),0);
    Eigen::Vector3d b2=b3.cross(heading);
    if(b2.norm()<1e-9) return;
    b2.normalize(); Eigen::Matrix3d Rd; Rd.col(0)=b2.cross(b3);Rd.col(1)=b2;Rd.col(2)=b3;
    const Eigen::Matrix3d E=.5*(Rd.transpose()*R_-R_.transpose()*Rd);
    const Eigen::Vector3d er(E(2,1),E(0,2),E(1,0));
    const Eigen::Vector3d moment=-kr_*er-kw_*omega_+omega_.cross(J_*omega_);
    Eigen::Vector4d wrench; wrench << A.dot(R_.col(2)),moment;
    const Eigen::Vector4d u=inverse_allocation_*wrench;
    if(!u.allFinite()) return;
    mav_msgs::Actuators msg;msg.header.stamp=now;msg.angular_velocities.resize(4);
    for(int i=0;i<4;++i)msg.angular_velocities[i]=std::copysign(std::sqrt(std::abs(u[i])),u[i]);
    rotor_pub_.publish(msg);
  }
};
int main(int argc,char** argv){ros::init(argc,argv,"controller_node");Controller node;ros::spin();return 0;}
