"""Implement the command line 'lnt' tool."""

import os
import sys
import tempfile
from optparse import OptionParser, OptionGroup

import StringIO
import lnt
import lnt.util.ImportData
from lnt import testing
from lnt.db import perfdb
from lnt.testing.util.commands import note, warning, error, fatal

def action_runserver(name, args):
    """start a new development server"""

    parser = OptionParser("%%prog %s [options] [<path|config file>]" % name)
    parser.add_option("", "--hostname", dest="hostname", type=str,
                      help="host interface to use [%default]",
                      default='localhost')
    parser.add_option("", "--port", dest="port", type=int, metavar="N",
                      help="local port to use [%default]", default=8000)
    parser.add_option("", "--reloader", dest="reloader", default=False,
                      action="store_true", help="use WSGI reload monitor")
    parser.add_option("", "--debugger", dest="debugger", default=False,
                      action="store_true", help="use WSGI debugger")
    parser.add_option("", "--threaded", dest="threaded", default=False,
                      action="store_true", help="use a threaded server")
    parser.add_option("", "--processes", dest="processes", type=int,
                      metavar="N", help="number of processes to use [%default]",
                      default=1)

    (opts, args) = parser.parse_args(args)
    if len(args) != 1:
        parser.error("invalid number of arguments")

    config, = args

    # Accept paths to config files, or to directories containing 'lnt.cfg'.
    if os.path.isdir(config):
        tmp = os.path.join(config, 'lnt.cfg')
        if os.path.exists(tmp):
            config = tmp

    if not config or not os.path.exists(config):
        raise SystemExit,"error: invalid config: %r" % config

    import lnt.server.ui.app
    instance = lnt.server.ui.app.App.create_standalone(
        config_path = config)
    if opts.debugger:
        instance.debug = True
    instance.run(opts.hostname, opts.port,
                 use_reloader = opts.reloader,
                 use_debugger = opts.debugger,
                 threaded = opts.threaded,
                 processes = opts.processes)

from create import action_create
from convert import action_convert
from import_data import action_import
from report import action_report
from updatedb import action_updatedb

def action_checkformat(name, args):
    """check the format of an LNT test report file"""

    parser = OptionParser("%%prog %s [options] files" % name)

    (opts, args) = parser.parse_args(args)
    if len(args) > 1:
        parser.error("incorrect number of argments")

    if len(args) == 0:
        input = '-'
    else:
        input, = args

    if input == '-':
        input = StringIO.StringIO(sys.stdin.read())

    db = lnt.server.db.v4db.V4DB('sqlite:///:memory:')
    result = lnt.util.ImportData.import_and_report(
        None, None, db, input, 'json', commit = True)
    lnt.util.ImportData.print_report_result(result, sys.stdout, sys.stderr,
                                            verbose = True)

def action_runtest(name, args):
    """run a builtin test application"""

    parser = OptionParser("%%prog %s test-name [options]" % name)
    parser.disable_interspersed_args()
    parser.add_option("", "--submit", dest="submit_url", metavar="URLORPATH",
                      help=("autosubmit the test result to the given server "
                            "(or local instance) [%default]"),
                      type=str, default=None)
    parser.add_option("", "--commit", dest="commit",
                      help=("whether the autosubmit result should be committed "
                            "[%default]"),
                      type=int, default=True)
    parser.add_option("", "--output", dest="output", metavar="PATH",
                      help="write raw report data to PATH (or stdout if '-')",
                      action="store", default=None)
    parser.add_option("-v", "--verbose", dest="verbose",
                      help="show verbose test results",
                      action="store_true", default=False)

    (opts, args) = parser.parse_args(args)
    if len(args) < 1:
        parser.error("incorrect number of argments")

    test_name,args = args[0],args[1:]

    import lnt.tests
    try:
        test_instance = lnt.tests.get_test_instance(test_name)
    except KeyError:
        parser.error('invalid test name %r' % test_name)

    report = test_instance.run_test('%s %s' % (name, test_name), args)

    if opts.output is not None:
        if opts.output == '-':
            output_stream = sys.stdout
        else:
            output_stream = open(opts.output, 'w')
        print >>output_stream, report.render()
        if output_stream is not sys.stdout:
            output_stream.close()

    # Save the report to a temporary file.
    #
    # FIXME: This is silly, the underlying test probably wrote the report to a
    # file itself. We need to clean this up and make it standard across all
    # tests. That also has the nice side effect that writing into a local
    # database records the correct imported_from path.
    tmp = tempfile.NamedTemporaryFile(suffix='.json')
    print >>tmp, report.render()
    tmp.flush()

    if opts.submit_url is not None:
        if report is None:
            raise SystemExit,"error: report generation failed"

        from lnt.util import ServerUtil
        test_instance.log("submitting result to %r" % (opts.submit_url,))
        ServerUtil.submitFile(opts.submit_url, tmp.name, True, opts.verbose)
    else:
        # Simulate a submission to retrieve the results report.

        # Construct a temporary database and import the result.
        test_instance.log("submitting result to dummy instance")
        db = lnt.server.db.v4db.V4DB("sqlite:///:memory:")
        result = lnt.util.ImportData.import_and_report(
            None, None, db, tmp.name, 'json', commit = True)
        lnt.util.ImportData.print_report_result(result, sys.stdout, sys.stderr,
                                                opts.verbose)

    tmp.close()

def action_showtests(name, args):
    """show the available built-in tests"""

    parser = OptionParser("%%prog %s" % name)
    (opts, args) = parser.parse_args(args)
    if len(args) != 0:
        parser.error("incorrect number of argments")

    import lnt.tests

    print 'Available tests:'
    test_names = lnt.tests.get_test_names()
    max_name = max(map(len, test_names))
    for name in test_names:
        print '  %-*s - %s' % (max_name, name,
                               lnt.tests.get_test_description(name))

def action_submit(name, args):
    """submit a test report to the server"""

    parser = OptionParser("%%prog %s [options] <url> <file>+" % name)
    parser.add_option("", "--commit", dest="commit", type=int,
                      help=("whether the result should be committed "
                            "[%default]"),
                      default=False)
    parser.add_option("-v", "--verbose", dest="verbose",
                      help="show verbose test results",
                      action="store_true", default=False)

    (opts, args) = parser.parse_args(args)
    if len(args) < 2:
        parser.error("incorrect number of argments")

    from lnt.util import ServerUtil
    ServerUtil.submitFiles(args[0], args[1:], opts.commit, opts.verbose)

###

commands = dict((name[7:], f) for name,f in locals().items()
                if name.startswith('action_'))
def main():
    cmds_width = max(map(len, commands))
    parser = OptionParser("""\
%%prog [options] <command> ... arguments ...

Available commands:
%s""" % ("\n".join("  %-*s - %s" % (cmds_width, name, func.__doc__)
                   for name, func in sorted(commands.items()))),
                          version = "lnt version %s" % lnt.__version__)
    parser.disable_interspersed_args()
    (opts, args) = parser.parse_args()

    if not args:
        parser.print_usage()
        return

    cmd = args[0]
    if cmd not in commands:
        parser.error("invalid command: %r" % cmd)

    commands[cmd](cmd, args[1:])

if __name__ == '__main__':
    main()
