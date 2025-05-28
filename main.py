#!/usr/bin/env python

import os
import sys
import subprocess
import yaml

def generate_ssh_string(host:str, username:str = None):
    """Generates an SSH connection string."""
    if username:
        return f"{username}@{host}"
    else:
        return host
    
def try_connection_to_slurmd_frontend(ssh_string:str):
    """Tries to connect to the SLURM frontend of the HPC cluster."""
    try:
        # Attempt to run a simple command on the remote host
        result = subprocess.run(["ssh", ssh_string, "scontrol ping"], capture_output=True, text=True, check=True)
        if "UP" in result.stdout:
            print(f"✅ Connection to {ssh_string} successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Connection failed: {e}")
        return False

def get_running_jobs_from_cluster(frontend:str, username:str = None):
    """connects to frontend of HPC cluster using ssh and gets the list of running jobs"""
    # ssh to the frontend
    # get the list of running jobs

    frontend = generate_ssh_string(frontend, username)

    if not try_connection_to_slurmd_frontend(frontend):
        print(f"❌ Failed to connect to {frontend}. Please check your SSH configuration for frontend {frontend}.")
        print("Exiting...")
        sys.exit(1)

    jobs = []
    command = "squeue --me --format=%all"  # example command to list jobs (for SLURM clusters)
    ssh_command = ["ssh", f"{frontend}", command]

    try:
        # Execute the SSH command
        result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
        jobs_output = result.stdout
        rc = result.returncode
        if rc != 0:
            raise subprocess.CalledProcessError(rc, ssh_command, output=jobs_output)

        # parse the output to get list of dicts:
        lines = jobs_output.splitlines()
        if not lines:
            return jobs

        keys = lines[0].split("|")
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split("|")
            if len(values) != len(keys):
                continue  # skip malformed lines
            job = {key: value for key, value in zip(keys, values)}
            job["frontend"] = frontend
            jobs.append(job)

    except subprocess.CalledProcessError as e:
        # print error if SSH command fails
        print(f"Error executing SSH command: {e}")
        
    return jobs



def load_config(config_path:str):
    """Loads a YAML configuration file."""
    with open(config_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)
    

def main():
    print("Hello from vscode4hpc!")

    homedir=os.path.expanduser("~")
    ssh_config_file = os.path.join(homedir, ".ssh", "config")

    #load config file
    config = load_config("config.yaml")
    print(f"ℹ️ Config loaded with {len(config['ssh_frontends'])} frontends.")

    # get the frontend from the config
    jobs_output = []
    for frontend in config["ssh_frontends"]:
        print(f"ℹ️ Connecting to frontend: {frontend['name']}")
        # get the running jobs from the cluster
        from_this_frontend = get_running_jobs_from_cluster(frontend['host'],frontend['username'])
        jobs_output.extend(from_this_frontend)
        if len(from_this_frontend) == 0:
            status_char = "ℹ️"
        else:
            status_char = "🟢"
        print(f"{status_char} Running jobs count {len(from_this_frontend)}" )
    
    # for every job, ensure there is corresponding entry in ~/.ssh/config

    ssh_aliases = []
    global_prefix = "_HPC"

    for job in jobs_output:

        print("👷 checking job:", job["JOBID"])

        job_name = job["NAME"]

        alias_prefix = f"{global_prefix}_{job['frontend']}"

        # extract the job port from the job name (s_32770) and check if it is a number
        if job_name.startswith("s_"):
            job_port = int(job_name[2:])
        else:
            continue

        ssh_alias_name = f"{alias_prefix}_{job["JOBID"]}"
        ssh_aliases.append(ssh_alias_name)

        # check if there is an entry in ~/.ssh/config for this host
        
        with open(ssh_config_file, 'r', encoding='utf-8') as file:
            ssh_config = file.read()

        if f"Host {ssh_alias_name}" not in ssh_config:
            print(f"▶️ Adding entry for {job["JOBID"]} to {ssh_config_file} as {ssh_alias_name} at port {job_port}")
            with open(ssh_config_file, 'a', encoding='utf-8') as file:
                file.write(f"\nHost {ssh_alias_name}\n")
                file.write(f"    User {job['USER']}\n")
                file.write("    CheckHostIP no\n")
                file.write("    StrictHostKeyChecking no\n")
                file.write("    UserKnownHostsFile /dev/null\n")
                file.write(f"    ProxyCommand ssh {job['USER']}@{job['frontend']} \"nc {job["EXEC_HOST"]} {job_port}\"\n")
                file.write(f"    Hostname {job["EXEC_HOST"]}\n")
                file.write(f"    Port {job_port}\n")
        else:
            print(f"ℹ️ Entry for {job["JOBID"]} already exists in {ssh_config_file} as {ssh_alias_name}")

    # make sure there are no hanging aliases in ~/.ssh/config
    with open(ssh_config_file, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    output_lines = []
    in_host_block = False
    old_host_block = False

    # state machine to parse and modify the ssh config file
    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.lower().startswith("host "):
            host_name = line.split()[1]
            if host_name.startswith(f"{global_prefix}_") and host_name not in ssh_aliases:
                print(f"⏹️ Removing entry for {host_name} from {ssh_config_file}")
                # remove the host block
                in_host_block = True
                old_host_block = True
            else:
                in_host_block = False
                output_lines.append(line)
        elif in_host_block:
            if line.strip() == "":
                in_host_block = False
                continue
            if old_host_block:
                continue
            output_lines.append(line)
        else:
            output_lines.append(line)

    # write the output lines back to the file
    with open(ssh_config_file, 'w', encoding='utf-8') as file:
        file.writelines(output_lines)

if __name__ == "__main__":
    main()
