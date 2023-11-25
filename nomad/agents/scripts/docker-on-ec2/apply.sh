#!/bin/bash

while getopts r:p:u:n:d:c:e:x:v: flag
do
	case "${flag}" in
		r) requirements=${OPTARG};;
		p) pem_path=${OPTARG};;
		u) user=${OPTARG};;
		n) public_dns_name=${OPTARG};;
		d) project_dir=${OPTARG};;
		c) copy_paths=${OPTARG};;
		e) env=${OPTARG};;
		x) post_build_cmds+=("$OPTARG");;
		v) python_version=${OPTARG};;
	esac
done

# ssh into the project so that we can authenticate our key
while true
do
  	errormessage=`ssh -o "StrictHostKeyChecking no" -i "${pem_path}" "${user}@${public_dns_name}" exit 2>/dev/null 2>&1`
    if [ -z "$errormessage" ]; then
        echo "SSH connection succeeded!"
        break
    else
		if [[ "$errormessage" =~ "Operation timed out" ]]; then
			echo "SSH connection failed."
			exit 8
		else
        	echo "SSH connection refused. Retrying in 5 seconds..."
        	sleep 5
		fi
    fi
done

# install Docker if it doesn't exist


# get project name and path as it would appear in cluster
project_name="$(basename -- ${project_dir})"
project_parent_dir="$(dirname ${project_dir})"

# convert the post-build commands to a string
NEWLINE=$'\n'
post_build_cmds_str=""
for val in "${post_build_cmds[@]}"; do
    post_build_cmds_str+="$val${NEWLINE}"
done

