#!/bin/bash

while getopts p:u:n:a:z:r:i: flag
do
	case "${flag}" in
		p) pem_path=${OPTARG};;
		u) user=${OPTARG};;
		n) public_dns_name=${OPTARG};;
		a) username=${OPTARG};;
		z) password=${OPTARG};;
		r) repository=${OPTARG};;
		i) image_name=${OPTARG};;
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
ssh -i ${pem_path} ${user}@${public_dns_name} "docker --version &> /dev/null";
exit_code=$?
if [ ! $exit_code -eq 0 ]; then
    echo "Docker is not installed. Installing Docker..."
    
	# Install Docker
	ssh -i ${pem_path} ${user}@${public_dns_name} "sudo yum update -y; sudo yum install -y docker; sudo service docker start; sudo usermod -a -G docker ${user}"
    echo "Docker has been installed."
else
    echo "Docker is already installed."
fi

# Log into Docker, pull the Docker image, and run
ssh -i ${pem_path} ${user}@${public_dns_name} "docker login --username ${username} --password ${password} ${repository}; docker pull ${repository//https:\/\//}/${image_name}";
