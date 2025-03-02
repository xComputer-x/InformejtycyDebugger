#!/bin/bash

debugger_slice_name=informejtycy_debugger.slice
max_containers_cpu_usage=60%

echo "Setting up a cgroup [v2]..."

/bin/bash -c 'echo "+cpu" > /sys/fs/cgroup/cgroup.subtree_control'
/bin/bash -c 'echo "+cpuset" > /sys/fs/cgroup/cgroup.subtree_control'

systemctl set-property $debugger_slice_name=informejtycy_debugger.slice CPUQuota=$max_containers_cpu_usage

echo "Cgroup [v2] has been made!"