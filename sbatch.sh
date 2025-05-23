#!/bin/bash

#SBATCH --time 12:00:00
#SBATCH --job-name sshd
#SBATCH --cpus-per-task 8
#SBATCH --mem 32G
#SBATCH --partition gpu_int
#SBATCH --gpus 1

# possibly uncomment the following line to load your modules
MODULES="CUDA/12.4.0"

# DOCUMENTATION:

# at your local machine / laptop, insert this into your ~/.ssh/config file:

# ----------------------------------------------------------

#Host phoebecn
#        User YourUser
#        CheckHostIP no
#        ProxyCommand ssh %r@phoebe.fzu.cz "nc \$(squeue --me --states=R -h --name=s_%p -O NodeList) %p"
#        StrictHostKeyChecking=no
#        UserKnownHostsFile=/dev/null

# ----------------------------------------------------------

# USE:

# start this job at your cluster, with sbatch sbatch.sh
# then, from your local machine, run:
# uv run main.py
# connect to the cluster with newly created ssh alias.


# make sure we have ssh host key for our user instance of SSH:

if [ ! -f ~/.ssh/ssh_host_rsa_key ]; then
    ssh-keygen -t rsa -f ~/.ssh/ssh_host_rsa_key -N ''
    chmod 600 ~/.ssh/ssh_host_rsa_key
fi

# generate sshd_config:
if [ -n "$MODULES" ]; then
    do_load_modules="module load ${MODULES}"
else
    do_load_modules="/usr/bin/true"
fi

echo "# filepath: ./sshd_config
Port 64321
HostKey ~/.ssh/ssh_host_rsa_key
PasswordAuthentication no
PermitRootLogin no
AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys
AuthorizedKeysCommandUser ${USER}
ForceCommand ${do_load_modules}; ${SHELL}
LogLevel VERBOSE" > ./sshd_config


# make sure we have the right permissions
chmod 600 ./sshd_config

# set random high unused tcp port and verify it is not in use
read SSHD_PORT upper_port < /proc/sys/net/ipv4/ip_local_port_range

isfree=$(netstat -taln | grep $SSHD_PORT)

while [[ -n "$isfree" ]]; do
    ((SSHD_PORT++))
    isfree=$(netstat -taln | grep $SSHD_PORT)
done

echo "SSH server will listen on port $SSHD_PORT"

scontrol update job=${SLURM_JOB_ID} comment="p_${SSHD_PORT}"
scontrol update job=${SLURM_JOB_ID} name="s_${SSHD_PORT}"


# run openSSH server:

/usr/sbin/sshd -D -e \
    -p ${SSHD_PORT} \
    -f ./sshd_config \
    -o PubkeyAuthentication=yes \
    -o ChallengeResponseAuthentication=no \
    -o PermitEmptyPasswords=no \
    -o PermitUserEnvironment=no \
    -o HostKey=/home/$USER/.ssh/ssh_host_rsa_key \
    -o SyslogFacility=AUTH \
    -o LogLevel=INFO \
    -o PidFile=/tmp/sshd_${SSHD_PORT}.pid
