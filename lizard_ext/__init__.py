''' extensions of lizard '''

from __future__ import print_function
from .htmloutput import html_output
from .xmloutput import xml_output
import lizardcpre

def print_xml(results, options, _):
    print(xml_output(list(results), options.verbose))
    return 0

CPreExtension = lizardcpre.LizardExtension()
