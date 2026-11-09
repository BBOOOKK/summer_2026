#include <ros/ros.h>
#include <tf/transform_broadcaster.h>
#include <trajectory_msgs/MultiDOFJointTrajectoryPoint.h>
#include <cmath>
int main(int argc,char**argv){
 ros::init(argc,argv,"traj_publisher");ros::NodeHandle n,p("~");
 auto pub=n.advertise<trajectory_msgs::MultiDOFJointTrajectoryPoint>("desired_state",1);
 double scale,hold,radius,height;p.param("time_scale",scale,2.0);p.param("acquisition_time",hold,8.0);p.param("radius",radius,5.0);p.param("height",height,2.0);
 bool smooth;p.param("smooth_start",smooth,true);ros::Time::waitForValid();const auto start=ros::Time::now();ros::Rate rate(100);tf::TransformBroadcaster br;
 while(ros::ok()){
 double t=(ros::Time::now()-start).toSec()-hold,w=1/scale,th=0,wd=0,wdd=0;
 if(t>=0){if(smooth&&t<4){double u=t/4;th=w*4*(2.5*pow(u,4)-3*pow(u,5)+pow(u,6));wd=w*(10*pow(u,3)-15*pow(u,4)+6*pow(u,5));wdd=w/4*(30*u*u-60*u*u*u+30*pow(u,4));}else{th=w*(t-(smooth?2:0));wd=w;}}
 trajectory_msgs::MultiDOFJointTrajectoryPoint m;m.transforms.resize(1);m.velocities.resize(1);m.accelerations.resize(1);
 auto& tr=m.transforms[0];tr.translation.x=radius*sin(th);tr.translation.y=radius*cos(th);tr.translation.z=height;
 tf::Quaternion q;q.setRPY(0,0,-th);tf::quaternionTFToMsg(q,tr.rotation);
 auto& v=m.velocities[0];v.linear.x=radius*cos(th)*wd;v.linear.y=-radius*sin(th)*wd;v.angular.z=-wd;
 auto& a=m.accelerations[0];a.linear.x=radius*(cos(th)*wdd-sin(th)*wd*wd);a.linear.y=-radius*(sin(th)*wdd+cos(th)*wd*wd);a.angular.z=-wdd;
 pub.publish(m);br.sendTransform(tf::StampedTransform(tf::Transform(q,tf::Vector3(tr.translation.x,tr.translation.y,tr.translation.z)),ros::Time::now(),"world","av-desired"));ros::spinOnce();rate.sleep();
 }
}
