#!/bin/bash

while getopts p:u:n:a:z:r:i:f:d: flag
do
	case "${flag}" in
		p) pem_path=${OPTARG};;
		u) user=${OPTARG};;
		n) public_dns_name=${OPTARG};;
		a) username=${OPTARG};;
		z) password=${OPTARG};;
		r) repository=${OPTARG};;
		i) image_name=${OPTARG};;
		f) download_files=${OPTARG};;
		d) project_dir=${OPTARG};;
	esac
done

# Test the SSH connection
while true
do
  	ssh -o "StrictHostKeyChecking no" -i "${pem_path}" "${user}@${public_dns_name}" exit 2>/dev/null 2>&1
    if [ $? -eq 0 ]; then
        break
    else
        echo "SSH connection failed. Retrying in 5 seconds..."
        sleep 5
    fi
done

# Run the Docker image
container_id=$(ssh -i ${pem_path} ${user}@${public_dns_name} "docker run -d ${repository//https:\/\//}/${image_name};")

# Check if container_id is not empty
if [ -n "$container_id" ]; then
	# Run docker logs for the container
	echo "Streaming logs for container ${container_id}"
    ssh -i ${pem_path} ${user}@${public_dns_name} "docker logs -f $container_id"
else
    echo "Failed to start the container."
fi

# Now, download the files
project_name="$(basename -- ${project_dir})"
for val in "${download_files[@]}"; do
	# Copy the file from the container to the instances
	ssh -i ${pem_path} ${user}@${public_dns_name} "docker cp $container_id:./${project_name}/${val} ${val}"
	exit_code=$?
	if [ $exit_code -eq 1 ]; then
		exit 1
	fi

	# Copy the file from the instance to local
	echo "Copying ${val} to local machine..."
	scp -i ${pem_path} ${user}@${public_dns_name}:${val} ${project_dir}/${val} 2> scp.log
	exit_code=$?
	if [ $exit_code -eq 1 ]; then
		exit 1
	fi
done
