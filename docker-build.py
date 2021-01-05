#!/usr/bin/env python

import argparse
import os
import random
import shutil
import string
import subprocess
import atexit


class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    NORMAL = '\033[0m'


def print_colored(color, text):
    """
    Prints colored text using Color class constants

    :param color: Color applied to the text
    :type color: str
    :param text: Text to print
    :type text: str
    """
    print(color + text + Color.NORMAL)


def random_string(num_characters):
    """
    Generates random alphanumeric string

    :param num_characters: Number of characters of generated string
    :type num_characters: int

    :returns Generated string
    :rtype str
    """
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(num_characters))


def parse_arg_array(arguments):
    """
    Parses array of arguments in key=value format into array
    where keys and values are values of the resulting array

    :param arguments: Arguments in key=value format
    :type arguments: list(str)

    :returns Arguments exploded by =
    :rtype list(str)
    """
    results = []
    for arg in arguments:
        results.extend(arg.split('=', 1))

    return results


def is_dir_empty(path):
    """
    Returns true if directory is empty

    :param path: Directory path
    :type path: str

    :returns True if directory is empty
    :rtype bool
    """
    return len(os.listdir(path)) == 0


def build_image(docker_context, dockerfile, image_name, docker_args, docker_build_args):
    """
    Builds Docker image specified by dockerfile path

    :param docker_context: Docker context relative to current working directory used during docker build
    :type docker_context: str
    :param dockerfile: Dockerfile path relative to current working directory
    :type dockerfile: str
    :param image_name: Docker image tag to label the final image with
    :type image_name: str
    :param docker_args: Arguments passed to docker command (arguments before the "build" directive)
    :type docker_args: list(str)
    :param docker_build_args: Arguments passed to docker build command
    :type docker_build_args: list(str)

    :returns Exit code from docker build operation
    :rtype int
    """

    arguments = ["docker"]
    arguments.extend(docker_args)
    arguments.extend(["build",
                      "--file", dockerfile,
                      "--tag", "%s:latest" % image_name,
                      "--pull"])
    arguments.extend(docker_build_args)
    arguments.extend([docker_context])

    print_colored(Color.BOLD, 'Building %s...' % dockerfile)
    print(' '.join(arguments))
    return subprocess.call(arguments)


def run_container(container_name, image_name, docker_args, docker_run_args):
    """
    Runs Docker container specified by image name

    :param container_name: Docker container name to identify the container created by this command
    :type container_name: str
    :param image_name: Docker image tag to label the final image with
    :type image_name: str
    :param docker_args: Arguments passed to docker command (arguments before the "run" directive)
    :type docker_args: list(str)
    :param docker_run_args: Arguments passed to docker run command
    :type docker_run_args: list(str)

    :returns Exit code from docker run operation
    :rtype int
    """

    arguments = ["docker"]
    arguments.extend(docker_args)
    arguments.extend(["run",
                      "--init",
                      "--name", container_name])
    arguments.extend(docker_run_args)
    arguments.extend(["%s:latest" % image_name])

    print_colored(Color.BOLD, 'Creating and running container %s...' % container_name)
    print(' '.join(arguments))
    return subprocess.call(arguments)


def remove_container(container_name, docker_args):
    """
    Removes Docker container specified by container name

    :param container_name: Docker container name to identify the container
    :type container_name: str
    :param docker_args: Arguments passed to docker command (arguments before the "rm" directive)
    :type docker_args: list(str)

    :returns Exit code from docker rm operation
    :rtype int
    """

    arguments = ["docker"]
    arguments.extend(docker_args)
    arguments.extend(["rm",
                      "--volumes",
                      "--force",
                      container_name])

    print_colored(Color.BOLD, 'Removing container %s...' % container_name)
    print(' '.join(arguments))
    with open(os.devnull, 'w') as devnull:
        return subprocess.call(arguments, stdout=devnull)


def get_container_workdir(container_name, docker_args):
    """
    Returns working directory inside Docker container specified by container name

    :param container_name: Docker container name to identify the container
    :type container_name: str
    :param docker_args: Arguments passed to docker command (arguments before the "inspect" directive)
    :type docker_args: list(str)

    :returns Working directory of Docker container
    :rtype str
    """

    arguments = ["docker"]
    arguments.extend(docker_args)
    arguments.extend(["inspect",
                      "--format", "{{.Config.WorkingDir}}",
                      container_name])

    print_colored(Color.BOLD, 'Getting workdir of container %s...' % container_name)
    print(' '.join(arguments))
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out = process.communicate()
    errcode = process.returncode
    if errcode != 0:
        print_colored(Color.YELLOW, 'WARN: Could not determine workdir of container %s, assuming "%s"' %
                      (container_name, os.path.sep))
        return os.path.sep

    workdir = out[0].decode('utf-8').strip()
    print_colored(Color.BOLD, 'Workdir of %s container is %s' % (container_name, workdir))
    return workdir


def copy_artifacts(container_name, dist_dir, out_dir, docker_args, docker_copy_args):
    """
    Copies artifacts from Docker container into local filesystem

    :param container_name: Docker container name to identify the container
    :type container_name: str
    :param dist_dir: Directory of artifacts inside Docker container relative to container working directory
    :type dist_dir: str
    :param out_dir: Directory of artifacts output directory in local filesystem relative to current working directory
    :type out_dir: str
    :param docker_args: Arguments passed to docker command (arguments before the "cp" directive)
    :type docker_args: list(str)
    :param docker_copy_args: Arguments passed to docker copy command
    :type docker_copy_args: list(str)

    :returns Exit code from docker cp operation
    :rtype int
    """

    if os.path.isabs(dist_dir):
        source_dir = dist_dir
    else:
        container_workdir = get_container_workdir(container_name, docker_args)
        source_dir = os.path.join(container_workdir, dist_dir)

    destination_dir = out_dir

    if os.path.isdir(destination_dir):
        print_colored(Color.BOLD, 'Removing old artifacts in %s...' % destination_dir)
        shutil.rmtree(destination_dir)

    arguments = ["docker"]
    arguments.extend(docker_args)
    arguments.extend(["cp"])
    arguments.extend(docker_copy_args)
    arguments.extend(["%s:%s" % (container_name, os.path.join(source_dir, '.')), destination_dir])

    print_colored(Color.BOLD, 'Copying build artifacts from %s to %s...' % (source_dir, destination_dir))
    print(' '.join(arguments))
    return subprocess.call(arguments)


def main(dist_dir=None, out_dir=None, dockerfile=None, docker_context=None, docker_args=None, docker_build_args=None,
         docker_run_args=None, docker_copy_args=None):
    """
    Builds Docker image, creates Docker container, copies artifacts and removes container

    :param dist_dir: Directory of artifacts inside Docker container relative to container working directory
    :type dist_dir: str
    :param out_dir: Directory of artifacts output directory in local filesystem relative to current working directory
    :type out_dir: str
    :param dockerfile: Dockerfile path relative to current working directory
    :type dockerfile: str
    :param docker_context: Docker context relative to current working directory used during docker build
    :type docker_context: str
    :param docker_args: Arguments passed to docker command (arguments before the "cp" directive)
    :type docker_args: list(str)
    :param docker_build_args: Arguments passed to docker build command
    :type docker_build_args: list(str)
    :param docker_run_args: Arguments passed to docker run command
    :type docker_run_args: list(str)
    :param docker_copy_args: Arguments passed to docker copy command
    :type docker_copy_args: list(str)

    :returns Exit code from the result of all operations
    :rtype int
    """

    image_name = random_string(8)
    container_name = random_string(8)

    print_colored(Color.BOLD, "Current working directory is: " + os.getcwd())

    build_return_code = build_image(docker_context, dockerfile, image_name, docker_args, docker_build_args)
    if build_return_code != 0:
        print_colored(Color.RED, "ERROR (%d) while building Docker image, exiting." % build_return_code)
        return build_return_code

    # On script exit, remove created container
    @atexit.register
    def exit_handler():
        remove_container(container_name, docker_args)

    run_return_code = run_container(container_name, image_name, docker_args, docker_run_args)
    if run_return_code != 0:
        print_colored(Color.RED, "ERROR (%d) while running Docker container, exiting." % run_return_code)
        return run_return_code

    copy_return_code = copy_artifacts(container_name, dist_dir, out_dir, docker_args, docker_copy_args)
    if copy_return_code != 0:
        print_colored(Color.RED, "ERROR (%d) while copying build artifacts, exiting." % copy_return_code)
        return copy_return_code

    if is_dir_empty(out_dir):
        print_colored(Color.YELLOW, "WARN: Successfully built, but there are no files in %s directory" % out_dir)
    else:
        print_colored(Color.GREEN, "Successfully built into %s" % out_dir)

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build project with Dockerfile.')
    parser.add_argument('--version', action='version', version='docker-build version 1.0')
    parser.add_argument('--dist-dir', required=True, help='Docker directory which contains build artifacts')
    parser.add_argument('--out-dir', help='Output directory into which copy build artifacts, '
                                          'relative to current working directory (or --workdir if set), '
                                          'defaults to --dist-dir')
    parser.add_argument('--workdir', default='.',
                        help='working directory where to execute scripts')
    parser.add_argument('--dockerfile', default='Dockerfile',
                        help='path to the Dockerfile relative to current working directory (or --workdir if set)')
    parser.add_argument('--docker-context', default='.',
                        help='context of docker build command relative to current working directory '
                             '(or --workdir if set)')
    parser.add_argument('--docker', dest='docker_args', metavar='DOCKER_ARGS', default=[], action='append',
                        help='any argument passed to docker calls, e.g. --docker="--host=127.0.0.1"')
    parser.add_argument('--docker-build', dest='docker_build_args', metavar='DOCKER_BUILD_ARGS', default=[],
                        action='append',
                        help='any argument passed to docker build call, e.g. --docker-build="--no-cache"')
    parser.add_argument('--docker-run', dest='docker_run_args', metavar='DOCKER_RUN_ARGS', default=[], action='append',
                        help='any argument passed to docker run call, e.g. --docker-run="--rm"')
    parser.add_argument('--docker-cp', dest='docker_copy_args', metavar='DOCKER_CP_ARGS', default=[], action='append',
                        help='any argument passed to docker cp call, e.g. --docker-cp="--archive"')

    args = vars(parser.parse_args())

    args['out_dir'] = args.get('dist_dir') if args.get('out_dir') is None else args.get('out_dir')
    args['docker_args'] = parse_arg_array(args.get('docker_args'))
    args['docker_run_args'] = parse_arg_array(args.get('docker_run_args'))
    args['docker_build_args'] = parse_arg_array(args.get('docker_build_args'))
    args['docker_copy_args'] = parse_arg_array(args.get('docker_copy_args'))

    os.chdir(args['workdir'])
    del args['workdir']

    return_code = main(**args)
    exit(return_code)