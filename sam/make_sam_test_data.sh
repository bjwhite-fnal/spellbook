#!/bin/bash

PREFIX=bjwhite_testfiles
FILETYPE=testfiles

# Generate a bunch of files of random data between 0-1Kb.
for n in {000..050}
do
    rand_int=$(( RANDOM + 2048*10 ))
    f_id=$(echo "$n")
    file_name="${PREFIX}_${f_id}.bin"
    # Create data file
    dd if=/dev/urandom of=data/${file_name} bs=1 count=${rand_int} > /dev/null 2>&1
    # Create matching metadata file
    echo "{\"file_name\": \"${file_name}\",\"file_size\": \"${rand_int}\",\"file_type\": \"${FILETYPE}\", \"group\": \"sam_bjwhite\"  }" > data/${file_name}.json
done


