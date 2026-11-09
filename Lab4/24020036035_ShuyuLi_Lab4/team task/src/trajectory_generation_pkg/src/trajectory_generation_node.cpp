// VNAV Lab4 Parts 1.1--1.3; original starter retained in reference/lab4.
#include <ros/ros.h>
#include <nav_msgs/Odometry.h>
#include <geometry_msgs/PoseArray.h>
#include <trajectory_msgs/MultiDOFJointTrajectoryPoint.h>
#include <mav_trajectory_generation/polynomial_optimization_linear.h>
#include <mav_trajectory_generation/trajectory.h>
#include <tf/transform_datatypes.h>
#include <fstream>
#include <iomanip>
#include <cmath>
#include <sstream>
class WaypointFollower {
  ros::Subscriber current_sub_, gates_sub_;
  ros::Publisher desired_pub_;
  ros::Timer timer_;
  ros::NodeHandle nh_;
  Eigen::Vector3d x_ = Eigen::Vector3d::Zero();
  double yaw_=0, scale_=1, vmax_=8, amax_=4, first_segment_factor_=1;
  double exit_distance_=0, exit_duration_=1, exit_speed_=5;
  double reference_lookahead_=0;
  std::string segment_factors_;
  int vertical_derivative_order_=4;
  std::string vertical_gate_velocities_;
  bool ready_=false;
  ros::Time start_;
  mav_trajectory_generation::Trajectory position_, yaw_path_, vertical_path_;
  Eigen::VectorXd evaluatePosition(double t,int derivative) const {
    Eigen::VectorXd result=position_.evaluate(t,derivative);
    if(!vertical_path_.empty()) result[2]=vertical_path_.evaluate(t,derivative)[0];
    return result;
  }
  void current(const nav_msgs::Odometry& msg) {
    // Part 1.1: measured world position.
    x_ << msg.pose.pose.position.x, msg.pose.pose.position.y, msg.pose.pose.position.z;
    yaw_=tf::getYaw(msg.pose.pose.orientation); ready_=true;
  }
  void plan(const geometry_msgs::PoseArray& msg) {
    if (!ready_ || msg.poses.empty() || !position_.empty()) return;
    using namespace mav_trajectory_generation;
    using namespace derivative_order;
    // Part 1.2: decoupled 3D position and unwrapped scalar yaw.
    Vertex::Vector vertices, yaws;
    Vertex first(3), first_yaw(1);
    first.makeStartOrEnd(x_, SNAP);
    first_yaw.makeStartOrEnd(Eigen::VectorXd::Constant(1,yaw_), SNAP);
    vertices.push_back(first); yaws.push_back(first_yaw);
    double last_yaw=yaw_;
    for (size_t i=0;i<msg.poses.size();++i) {
      const auto& pose=msg.poses[i];
      Eigen::Vector3d p(pose.position.x,pose.position.y,pose.position.z);
      Vertex v(3), y(1);
      double raw=tf::getYaw(pose.orientation);
      double continuous=last_yaw+std::atan2(std::sin(raw-last_yaw),std::cos(raw-last_yaw));
      if (i+1==msg.poses.size() && exit_distance_<=0) {
        v.makeStartOrEnd(p,SNAP);
        y.makeStartOrEnd(Eigen::VectorXd::Constant(1,continuous),SNAP);
      } else { v.addConstraint(POSITION,p); y.addConstraint(ORIENTATION,continuous); }
      if (i+1==msg.poses.size() && exit_distance_>0) {
        Eigen::Vector3d direction(std::cos(raw),std::sin(raw),0);
        if(i>0) {
          const auto& prev=msg.poses[i-1].position;
          if(direction.dot(p-Eigen::Vector3d(prev.x,prev.y,prev.z))<0) direction=-direction;
        }
        v.addConstraint(VELOCITY,exit_speed_*direction);
      }
      vertices.push_back(v); yaws.push_back(y); last_yaw=continuous;
    }
    if(exit_distance_>0) {
      const auto& pose=msg.poses.back();
      Eigen::Vector3d p(pose.position.x,pose.position.y,pose.position.z);
      Eigen::Vector3d direction(std::cos(last_yaw),std::sin(last_yaw),0);
      const auto& prev=msg.poses[msg.poses.size()>1?msg.poses.size()-2:0].position;
      if(direction.dot(p-Eigen::Vector3d(prev.x,prev.y,prev.z))<0) direction=-direction;
      Vertex end(3),end_yaw(1);
      end.makeStartOrEnd(p+exit_distance_*direction,SNAP);
      end_yaw.makeStartOrEnd(Eigen::VectorXd::Constant(1,last_yaw),SNAP);
      vertices.push_back(end);yaws.push_back(end_yaw);
    }
    auto times=estimateSegmentTimes(vertices,vmax_,amax_);
    for (auto& t:times) t*=scale_;
    times.front()*=first_segment_factor_;
    // Optional per-segment timing: keep the exact gate-centre constraints,
    // spend more time in sharp bends and less on easier sections.
    if(!segment_factors_.empty()) {
      std::stringstream input(segment_factors_); std::string item; size_t i=0;
      while(std::getline(input,item,',')) {
        if(i>=msg.poses.size()) throw std::runtime_error("Too many segment factors");
        const double factor=std::stod(item);
        if(!std::isfinite(factor) || factor<=0) throw std::runtime_error("Segment factors must be positive");
        times[i++]*=factor;
      }
      if(i!=msg.poses.size()) throw std::runtime_error("Supply one timing factor per gate");
    }
    if(exit_distance_>0) times.back()=exit_duration_;
    PolynomialOptimization<10> opt(3), yaw_opt(1);
    opt.setupFromVertices(vertices,times,SNAP); opt.solveLinear();
    yaw_opt.setupFromVertices(yaws,times,SNAP); yaw_opt.solveLinear();
    opt.getTrajectory(&position_); yaw_opt.getTrajectory(&yaw_path_);
    if(vertical_derivative_order_!=4 || !vertical_gate_velocities_.empty()) {
      Vertex::Vector zs;
      for(const auto& vertex:vertices) {
        Vertex z(1);
        vertex.getSubdimension({2},SNAP,&z);zs.push_back(z);
      }
      if(!vertical_gate_velocities_.empty()) {
        std::stringstream input(vertical_gate_velocities_);std::string item;size_t i=1;
        while(std::getline(input,item,',')) {
          if(i>msg.poses.size()) throw std::runtime_error("Too many vertical gate velocities");
          if(item!="auto") zs[i].addConstraint(VELOCITY,std::stod(item));
          ++i;
        }
        if(i!=msg.poses.size()+1) throw std::runtime_error("Supply one vertical velocity entry per gate");
      }
      PolynomialOptimization<10> z_opt(1);
      z_opt.setupFromVertices(zs,times,vertical_derivative_order_);z_opt.solveLinear();z_opt.getTrajectory(&vertical_path_);
    }
    std::string output;
    if (nh_.getParam("plan_output",output)) {
      std::ofstream f(output);
      f << std::setprecision(12) << "t,x,y,z,vx,vy,vz,ax,ay,az,yaw\n";
      for(double t=0;t<=position_.getMaxTime()+0.005;t+=0.01) {
        double u=std::min(t,position_.getMaxTime());
        auto p=evaluatePosition(u,POSITION), v=evaluatePosition(u,VELOCITY), a=evaluatePosition(u,ACCELERATION);
        f<<u; for(int j=0;j<3;++j) f<<","<<p[j];
        for(int j=0;j<3;++j) f<<","<<v[j];
        for(int j=0;j<3;++j) f<<","<<a[j];
        f<<","<<yaw_path_.evaluate(u,ORIENTATION)[0]<<"\n";
      }
      std::ofstream g(output+".times"); double total=0;
      for(auto t:times) { total+=t;g<<std::setprecision(12)<<total<<"\n"; }
    }
    start_=ros::Time::now();
    ROS_INFO("LAB4_PLAN duration=%.6f gates=%zu scale=%.3f",position_.getMaxTime(),msg.poses.size(),scale_);
  }
  void publish(const ros::TimerEvent&) {
    if(position_.empty()) return;
    using namespace mav_trajectory_generation::derivative_order;
    // Part 1.3: simulator time, clamped to terminal hover.
    double elapsed=std::max(0.0,(ros::Time::now()-start_).toSec());
    double t=std::min(elapsed+reference_lookahead_,position_.getMaxTime());
    auto p=evaluatePosition(t,POSITION),v=evaluatePosition(t,VELOCITY),a=evaluatePosition(t,ACCELERATION);
    double yaw=yaw_path_.evaluate(t,ORIENTATION)[0];
    trajectory_msgs::MultiDOFJointTrajectoryPoint out;
    out.time_from_start=ros::Duration(t);
    out.transforms.resize(1); out.velocities.resize(1); out.accelerations.resize(1);
    auto& tr=out.transforms[0]; tr.translation.x=p[0];tr.translation.y=p[1];tr.translation.z=p[2];
    tr.rotation=tf::createQuaternionMsgFromYaw(yaw);
    auto& vel=out.velocities[0];vel.linear.x=v[0];vel.linear.y=v[1];vel.linear.z=v[2];
    vel.angular.z=yaw_path_.evaluate(t,VELOCITY)[0];
    auto& acc=out.accelerations[0];acc.linear.x=a[0];acc.linear.y=a[1];acc.linear.z=a[2];
    acc.angular.z=yaw_path_.evaluate(t,ACCELERATION)[0];
    if(nh_.param("publish_jerk",false)) {
      const auto jerk=evaluatePosition(t,JERK);
      acc.angular.x=jerk[0];acc.angular.y=jerk[1];acc.angular.z=jerk[2];
    }
    desired_pub_.publish(out);
  }
 public:
  WaypointFollower():nh_("~") {
    nh_.param("time_scale",scale_,1.0);nh_.param("v_max",vmax_,8.0);nh_.param("a_max",amax_,4.0);
    nh_.param("first_segment_factor",first_segment_factor_,1.0);
    nh_.param("reference_lookahead",reference_lookahead_,0.0);
    nh_.param<std::string>("segment_factors",segment_factors_,"");
    nh_.param("vertical_derivative_order",vertical_derivative_order_,4);
    nh_.param<std::string>("vertical_gate_velocities",vertical_gate_velocities_,"");
    if(vertical_derivative_order_<2 || vertical_derivative_order_>4) throw std::runtime_error("Vertical derivative order must be 2, 3 or 4");
    nh_.param("exit_distance",exit_distance_,0.0);nh_.param("exit_duration",exit_duration_,1.0);nh_.param("exit_speed",exit_speed_,5.0);
    if(scale_<=0 || vmax_<=0 || amax_<=0) throw std::runtime_error("Timing parameters must be positive");
    current_sub_=nh_.subscribe("/current_state",1,&WaypointFollower::current,this);
    gates_sub_=nh_.subscribe("/desired_traj_vertices",1,&WaypointFollower::plan,this);
    desired_pub_=nh_.advertise<trajectory_msgs::MultiDOFJointTrajectoryPoint>("/desired_state",1);
    timer_=nh_.createTimer(ros::Duration(0.01),&WaypointFollower::publish,this);
  }
};
int main(int argc,char** argv) {
  ros::init(argc,argv,"trajectory_generation_node");
  WaypointFollower follower; ros::spin(); return 0;
}
