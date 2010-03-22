"""
Utilities for converting to LNT's test format.
"""

from AppleOpenSSLReader import format as apple_openssl
from NightlytestReader import format as nightlytest
from PlistFormat import format as plist
from JSONFormat import format as json

# FIXME: Lazy loading would be nice.
formats = [plist, json, nightlytest, apple_openssl]
formats_by_name = dict((f['name'], f) for f in formats)
format_names = formats_by_name.keys()

def get_format(name):
    return formats_by_name.get(name)
    
def guess_format(path_or_file):
    """guess_format(path_or_file) -> [format]

    Guess which format should be used to load the given file and return it, if
    found.
    """

    # Check that files are seekable.
    is_file = False
    if not isinstance(path_or_file, str):
        is_file = True
        path_or_file.seek(0)

    matches = None
    for f in formats:
        # Check if the path matches this format, ignoring exceptions.
        try:
            try:
                if not f['predicate'](path_or_file):
                    continue
            except:
                continue
        finally:
            if is_file:
                # Reset seek.
                path_or_file.seek(0)

        # Reject anything which matches multiple formats.
        if matches:
            return None

        matches = f

    return matches

def read_any(path_or_file, format_name):
    # Figure out the input format.
    if format_name == '<auto>':
        f = guess_format(path_or_file)
        if f is None:
            if isinstance(path_or_file, str):
                raise SystemExit("unable to guess input format for %r" % input)
            else:
                raise SystemExit("unable to guess input format for file")
    else:
        f = get_format(format_name)
        if f is None or not f.get('read'):
            raise SystemExit("unknown input format: %r" % inFormat)

    return f['read'](path_or_file)
