#!/usr/bin/env python

import os
import subprocess
import yaml

def get_running_jobs_from_cluster(frontend:str):
    """connects to frontend of HPC cluster using ssh and gets the list of running jobs"""
    # ssh to the frontend
    # get the list of running jobs

    command = "squeue --me --format=%all"  # example command to list jobs (for SLURM clusters)

    ssh_command = ["ssh", f"{frontend}", command]

    jobs = []

    try:
        # Execute the SSH command
        #print("Executing command:", ssh_command)
        result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
        jobs_output = result.stdout

        # returns something like:
        # ACCOUNT|TRES_PER_NODE|MIN_CPUS|MIN_TMP_DISK|END_TIME|FEATURES|GROUP|OVER_SUBSCRIBE|JOBID|NAME|COMMENT|TIME_LIMIT|MIN_MEMORY|REQ_NODES|COMMAND|PRIORITY|QOS|REASON|ST|USER|RESERVATION|WCKEY|EXC_NODES|NICE|S:C:T|JOBID|EXEC_HOST|CPUS|NODES|DEPENDENCY|ARRAY_JOB_ID|GROUP|SOCKETS_PER_NODE|CORES_PER_SOCKET|THREADS_PER_CORE|ARRAY_TASK_ID|TIME_LEFT|TIME|NODELIST|CONTIGUOUS|PARTITION|PRIORITY|NODELIST(REASON)|START_TIME|STATE|UID|SUBMIT_TIME|LICENSES|CORE_SPEC|SCHEDNODES|WORK_DIR
        # fzu_a_39|N/A|8|0|2025-05-23T03:41:42|(null)|jose|OK|3205536|s_32770|p_32770|12:00:00|32G||/home/jose/projects/nvidia_container_apptainer/sbatch.sh|0.00000291038305|max400cpu|None|R|jose|(null)|(null)||0|*:*:*|3205536|gpu1|8|1|(null)|3205536|30012|*|*|*|N/A|11:40:14|19:46|gpu1|0|gpu_int|12500|gpu1|2025-05-22T15:41:42|RUNNING|30012|2025-05-22T15:41:38|(null)|N/A|(null)|/home/jose/projects/nvidia_container_apptainer
        # fzu_a_39|N/A|8|0|2025-05-23T03:38:01|(null)|jose|OK|3205535|s_32769|p_32769|12:00:00|32G||/home/jose/projects/nvidia_container_apptainer/sbatch.sh|0.00000291038305|max400cpu|None|R|jose|(null)|(null)||0|*:*:*|3205535|gpu1|8|1|(null)|3205535|30012|*|*|*|N/A|11:36:33|23:27|gpu1|0|gpu_int|12500|gpu1|2025-05-22T15:38:01|RUNNING|30012|2025-05-22T15:38:01|(null)|N/A|(null)|/home/jose/projects/nvidia_container_apptainer

        # parse the output to get list of dicts:

        keys = jobs_output.splitlines()[0].split("|")

        for line in jobs_output.splitlines()[1:]:
            values = line.split("|")
            job = {}
            for i, key in enumerate(keys):
                job[key] = values[i]
            job["frontend"] = frontend
            jobs.append(job)

    except subprocess.CalledProcessError as e:
        jobs_output = f"Error: {e}"
        
    return jobs



def load_config(config_path):
    """Loads a YAML configuration file."""
    with open(config_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)
    

def main():
    print("Hello from vscode4hpc!")

    homedir=os.path.expanduser("~")
    ssh_config_file = os.path.join(homedir, ".ssh", "config")

    #load config file
    config = load_config("config.yaml")
    print("Loaded config:", config)

    # get the frontend from the config
    jobs_output = []
    for frontend in config["ssh_frontends"]:
        print("Frontend:", frontend)
        # get the running jobs from the cluster
        jobs_output.extend(get_running_jobs_from_cluster(frontend['host']))
        print("Running jobs count", len(jobs_output))
    
    # for every job, ensure there is corresponding entry in ~/.ssh/config

    ssh_aliases = []
    global_prefix = "_HPC"

    for job in jobs_output:

        print("checking job:", job["JOBID"])

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
            print(f"Adding entry for {job["JOBID"]} to {ssh_config_file} as {ssh_alias_name} at port {job_port}")
            with open(ssh_config_file, 'a', encoding='utf-8') as file:
                file.write(f"\nHost {ssh_alias_name}\n")
                file.write(f"    User {job['USER']}\n")
                file.write("    CheckHostIP no\n")
                file.write("    StrictHostKeyChecking no\n")
                file.write("    UserKnownHostsFile /dev/null\n")
                file.write(f"    ProxyCommand ssh {job['USER']}@{job['frontend']} \"nc {job["EXEC_HOST"]} {job_port}\"\n")
                file.write(f"    Hostname {job["EXEC_HOST"]}\n")
                file.write(f"    Port {job_port}\n")

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
                print(f"Removing entry for {host_name} from {ssh_config_file}")
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
