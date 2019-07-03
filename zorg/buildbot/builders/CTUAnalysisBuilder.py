from buildbot.process.properties import WithProperties
from buildbot.steps.shell import ShellCommand
from buildbot.steps.slave import RemoveDirectory

from zorg.buildbot.builders import UnifiedTreeBuilder


def wrapCommandForAnalysis(command, cwd='.'):
    """ Extends a command line invocation by setting the environment for using
        the built unified tree binaries, and activating CodeChecker virtualenv.

    Parameters:
        command (str): The command to be run in the analysis environment.
        cwd (str): The intended working directory of the command to be run.

    Returns:
        str: An extended command that uses the analysis environment.

    """

    usingClangAndVenv = (
        'export PATH="$(realpath build/bin):'
        '$(realpath codechecker/build/CodeChecker/bin):$PATH" '
        '&& source codechecker/venv/bin/activate')

    return 'bash -c \'{prefix} && cd "{cwd}" && {command}\''.format(
        prefix=usingClangAndVenv, command=command, cwd=cwd)


def makeAnalysisShellCommand(*args, **kwargs):
    """ Adjusts the arguments intended for a ShellCommand in order to provide
    transparent usage of Clang and CodeChecker.

    Parameters:
        *args (list): Arbitrary positional arguments passed forward to
            ShellCommand.
        **kwargs (dict): Arbitrary positional arguments passed forward to
            ShellCommand, but command, and workdir keys are modified.

    Returns:
        ShellCommand: An instance, which uses an environment that satisfies
        the requirements of CodeChecker.

    """

    if 'command' in kwargs:
        command = kwargs['command']
        if isinstance(command, list):
            command = ' '.join(command)

        cwd = kwargs.get('workdir', '.')
        kwargs['command'] = wrapCommandForAnalysis(command, cwd)
        kwargs['workdir'] = '.'

    return ShellCommand(*args, **kwargs)


def shallowCloneTagCommand(url, tag):
    """ Assembles a command that makes a shallow clone of a git repository.

    Parameters:
        url (str): The url of the git repository.
        tag (str): The needed tag of the the repository. Depending on the git
                   server hashes may be supported, but its not guaranteed.
    Returns:
        str: The command string. Intended to be run in an empty directory.

    """

    return (
        'git init && '
        'git remote add origin "{url}" && '
        'git fetch --depth 1 origin {tag} && '
        'git checkout FETCH_HEAD').format(url=url, tag=tag)


def getFactory(
        clean=False,
        extra_configure_args=None,
        env=None,
        **kwargs):
    """ Creates a Builder, which can handle the changes related to the LLVM
        and Clang codebase with respect to their effects on CTU analysis. Uses
        CodeChecker as the analysis driver.

    Parameters:
        clean (bool): Indicates whether Clang should be rebuilt during the
            current run.
        extra_configure_args (dict of str: str): Extra arguments provided to
            the CMake invocation.
        env (dict of str: str): Extra environmental variables for the shell.
        **kwargs: Extra keyword argument passed forward to the Builder.

    Returns:
        A Builder instance that contains steps for running CTU Analysis on TMUX
        via CodeChecker.

    """

    f = UnifiedTreeBuilder.getCmakeWithNinjaBuildFactory(
            depends_on_projects=['llvm', 'clang'],
            checks=[],
            clean=clean,
            extra_configure_args=extra_configure_args,
            env=env,
            **kwargs)

    # Build properties override default values for CodeChecker repository url
    # and version tag.
    cc_url = '%(codechecker_url:-{default})s'.format(
        default='https://github.com/Ericsson/codechecker.git')
    cc_tag = '%(codechecker_tag:-{default})s'.format(
        default='v6.9.1')

    f.addStep(
        ShellCommand(
            name='Delete CodeChecker directory',
            command=(['rm', '-rf', 'codechecker']),
            haltOnFailure=True,
            description=['Delete', 'CodeChecker'],
            workdir='.',
            env=env))

    # Download CodeChecker source.
    f.addStep(
        ShellCommand(
            name='Download CodeChecker',
            command=WithProperties(shallowCloneTagCommand(cc_url, cc_tag)),
            haltOnFailure=True,
            description=['Download', 'CodeChecker'],
            workdir='codechecker',
            env=env))

    # Build CodeChecker virtualenv.
    f.addStep(
        ShellCommand(
            name='Build CodeChecker venv',
            command=['make', 'venv'],
            haltOnFailure=True,
            description=[
                'Make', 'virtual', 'environment', 'for', 'CodeChecker'],
            workdir='codechecker',
            env=env))

    # Build CodeChecker package.
    f.addStep(
        makeAnalysisShellCommand(
            name='Build CodeChecker package',
            command=['make', 'package'],
            haltOnFailure=True,
            description=[
                'Build', 'CodeChecker', 'package', 'used', 'for', 'analysis'],
            workdir='codechecker',
            env=env))

    # Provide default values for analysis target 'tmux'.
    DEFAULT_TMUX_URL = 'https://github.com/tmux/tmux.git'
    DEFAULT_TMUX_TAG = '2.6'

    # Build properties override defaults.
    tmux_url = '%(tmux_url:-{default})s'.format(default=DEFAULT_TMUX_URL)
    tmux_tag = '%(tmux_tag:-{default})s'.format(default=DEFAULT_TMUX_TAG)

    # Clean tmux.
    f.addStep(
        RemoveDirectory(
            name='Delete tmux',
            dir='tmux',
            haltOnFailure=True))

    # Download tmux source.
    f.addStep(
        ShellCommand(
            name='Download tmux',
            command=WithProperties(
                shallowCloneTagCommand(tmux_url, tmux_tag)),
            haltOnFailure=True,
            description=['Download', 'tmux'],
            workdir='tmux',
            env=env))

    # Configure tmux.
    f.addStep(
        ShellCommand(
            name='Configure tmux',
            command='./autogen.sh && ./configure',
            haltOnFailure=True,
            description=['Configure', 'tmux', 'project'],
            workdir='tmux',
            env=env))

    # Log tmux with CodeChecker.
    f.addStep(
        makeAnalysisShellCommand(
            name='Log tmux with CodeChecker',
            command=[
                'CodeChecker', 'log',
                '--output', 'compile_commands.json',
                '-b', 'make'],
            haltOnFailure=True,
            description=['Log', 'tmux', 'build', 'with', 'CodeChecker'],
            workdir='tmux',
            env=env))

    # Make .sa_args file to disable macro expansion.
    f.addStep(
        ShellCommand(
            name='Create file to disable macro expansion',
            command=(
                "echo '-Xclang -analyzer-config -Xclang expand-macros=false '"
                " > .sa_args"),
            haltOnFailure=True,
            description=[
                'Create', '.sa_args', 'file', 'to', 'disable', 'macro',
                'expansion'],
            workdir='tmux',
            env=env))

    # Clean tmux results.
    f.addStep(
        RemoveDirectory(
            name='Delete tmux results',
            dir='tmux_results',
            haltOnFailure=True
            #, description=['Delete', 'the', 'tmux', 'results', 'directory']
            #, workdir='.'
            ))

    # Analyze tmux using CodeChecker.
    f.addStep(
        makeAnalysisShellCommand(
            name='Analyze tmux',
            command=[
                'CodeChecker', 'analyze',
                '--output', 'tmux_results',
                '--saargs', 'tmux/.sa_args',
                '--jobs', '1',
                '--verbose', 'debug',
                'tmux/compile_commands.json'],
            haltOnFailure=True,
            description=['Analyze', 'tmux', 'in', 'CTU', 'mode'],
            workdir='.',
            env=env))

    return f
