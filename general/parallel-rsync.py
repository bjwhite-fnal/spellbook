# Parallel rsync Transfer Program
# Transfers files/directories from remote rsync servers load-balanced
#     round-robin in parallel to a local filesystem using rsync
# Brandon White, 2022

import argparse
import getpass
import logging
import os
import os.path
import shutil
import subprocess
import tempfile
from multiprocessing import Process, Queue

logging.basicConfig(format='%(asctime)-15s %(name)s %(levelname)s %(message)s', level=logging.INFO)
logger = logging.getLogger()

class Sentinel:
    pass

def execute_transfer(pid, local_directory, remote_host, transfer_path, user, pwd_f, fail_logger):
    module = 'LSSTUser' # TODO: Make this an actual argument
    remote_source = f'{user}@{remote_host}::{module}/{transfer_path}'
    format_string = '--out-format=\"%o %m %i %n %l %C\"' # TODO: Make this an actual argument
    pwd_arg = f'--password-file={pwd_f}'
    logger.info(f'(pid:{pid}) Executing transfer of {transfer_path} from {remote_host} to {local_directory}\n\t\
            rsync --archive --relative --xattrs {pwd_arg} {format_string} {remote_source} {local_directory}')
    xfer_process = subprocess.Popen([
        'rsync',
        '--archive',
        #'--relative',
        '--xattrs',
        pwd_arg,
        format_string,
        remote_source,
        local_directory
    ], stdout=subprocess.PIPE)
    xfer_stdout, xfer_stderr = xfer_process.communicate()
    logger.info(f'(pid:{pid}) {xfer_stdout.decode().strip()}')
    if xfer_process.returncode != 0:
        logger.info(f'!!!  TRANSFER FAILURE: {remote_source}')
        fail_logger.error(transfer_path)

def do_processing(pid, transfer_queue, args):
    fail_log_path = os.path.join(args.fail_log_path, f'{os.path.basename(args.transfer_info_f)}.{pid}.error') 
    fail_logger = logging.getLogger('fail_log')
    fh = logging.FileHandler(fail_log_path)
    fail_logger.addHandler(fh)

    remote_hosts = args.remotehosts.split(',')
    i = 0
    while True:
        transfer_path = transfer_queue.get()
        if isinstance(transfer_path, Sentinel):
            logger.info(f'PID: {pid} complete. Waiting to join.')
            return
        remote_host_index = i % len(remote_hosts) # Incrementally select the next host round-robin for load-balancing
        execute_transfer(pid, args.localdirectory, remote_hosts[remote_host_index], transfer_path, args.user, args.password_file, fail_logger)
        i += 1

def get_program_arguments():
    parser = argparse.ArgumentParser(description='Transfers a directory from a remote host(s) in parallel to a given local filesystem using rsync')
    parser.add_argument('remotehosts', type=str, help='Remote hostname to transfer from. \
            May be provided as a comma-separated list of hostnames to cycle through.\n\
            All hostnames must have the same view of the transfer source filesystem.')
    parser.add_argument('localdirectory', type=str, help='Local directory that is the \
            destination of the transfer operation.')
    parser.add_argument('transfer_info_f', type=str, help='File containing one file path on the remote host per line')
    parser.add_argument('password_file', type=str, help='When running in daemon mode, you are gonna want this.')
    parser.add_argument('--num-procs', type=int, default=1, help='Number of procs to divy up lines .')
    parser.add_argument('--ignore-checkpoint', default=False, action='store_true')
    parser.add_argument('--user', type=str, default=getpass.getuser(), help='User to execute the rsync as. \
            Defaults to current linux user.')
    parser.add_argument('--fail-log-path', type=str, default=f'/sdf/group/rubin/scratch/transfer_lists/error_files',
            help='User to execute the rsync as. Defaults to current linux user.')

    args = parser.parse_args()
    return args

def main():
    args = get_program_arguments()
    logstr = f'Executing transfer with the following parameters:\n\
            \tRemote Host(s): {args.remotehosts}\n\
            \tLocal Directory (transfer destination): {args.localdirectory}\n\
            \tNum Procs: {args.num_procs}\n\
            \tUser: {args.user}'
    logger.info(logstr)

    if not os.path.isdir(args.localdirectory):
        os.mkdir(args.localdirectory)
    
    procs = []
    transfer_queue = Queue(args.num_procs)
    logger.info(f'Starting {args.num_procs} procs')
    for i in range(args.num_procs):
        p = Process(target=do_processing, args=(i, transfer_queue, args))
        p.start()
        procs.append(p)

    # See if there is a point in the input file we should resume at
    start_from = 0
    fmarkfile_path = f'{args.transfer_info_f}.resume'
    if not args.ignore_checkpoint:
        try:
            logger.info(f'Checking {fmarkfile_path} for a line offset...')
            with open(fmarkfile_path, 'r') as fmarkfile:
                start_from = int(fmarkfile.read())
        except OSError:
            pass
    logger.info(f'Starting processing from {start_from} lines into the input file...')

    with open(args.transfer_info_f) as f: # Obtain the work distribution and hand it to the procs
        for i, item in enumerate(f):
            if i < start_from:
                if i < 10 or i % 500 == 0:
                    logger.info(f'Scrolling to where we left off...')
                continue
            transfer_item = item.strip()
            transfer_queue.put(transfer_item)
            if i % 500 == 0:
                temp_f = tempfile.NamedTemporaryFile(mode='wt', delete=False)
                temp_f.write(str(i))
                temp_fname = temp_f.name
                temp_f.close()
                shutil.copy(temp_fname, fmarkfile_path)
                os.remove(temp_fname)
            
    logger.info('All transfer items produced to consumer processes. Dispatching Sentinel.')
    for i in range(args.num_procs):
        transfer_queue.put(Sentinel())
    for p in procs:
        p.join()

if __name__ == "__main__":
    main()
