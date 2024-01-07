#!/bin/bash

while getopts p:u:n:d:c:f: flag
do
	case "${flag}" in
		p) pem_path=${OPTARG};;
		u) user=${OPTARG};;
		n) public_dns_name=${OPTARG};;
		d) project_dir=${OPTARG};;
		c) command=${OPTARG};;
		f) download_files+=("$OPTARG");;
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

# Run the Prism command via SSH
project_name="$(basename -- ${project_dir})"
ssh -i ${pem_path} ${user}@${public_dns_name} "source ~/.venv/${project_name}/bin/activate; cd ../..; cd ${project_dir}; ${command}"
exit_code=$?
if [ $exit_code -eq 1 ]; then
	exit 1
fi

# Now, download the files
for val in "${download_files[@]}"; do
	echo "Copying ${val} to local machine..."
	scp -i ${pem_path} ${user}@${public_dns_name}:../../${project_dir}/${val} ${project_dir}/${val} 2> scp.log
	exit_code=$?
	if [ $exit_code -eq 1 ]; then
		exit 1
	fi
done
