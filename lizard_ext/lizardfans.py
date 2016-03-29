"""
This is an extension to lizard. It count the structural
fan in and fan out of every procedures in the source code
which can be described as:
SFIN (procedure) = number of procedures that call this procedure
SFOUT (procedure) = number of procedures this procedure calls
If agreed upon, Henry's and Kafura's Complexity Metric will be
calculated and integrated.
"""

import re
from sys import stderr


class LizardExtension(object):  # pylint: disable=R0903

    FUNCTION_CAPTION = ["  fan_in  ", "  fan_out  "]
    FUNCTION_INFO_PART = ["fan_in", "fan_out"]

    def __init__(self):
        self.name_list = []

    @staticmethod
    def __call__(tokens, reader):
        """
        The function will be used in multiple threading tasks.
        So don't store any data with an extension object.
        """
        reader.context.fileinfo.fan_in = reader.context.fileinfo.fan_out = 0
        return tokens

    def fans(self, fileinfo):
        """
        Preparation of calculating the fan in and fan out (prototype)
        """
        self.name_list = [func.name for func in fileinfo.function_list]
        for func in fileinfo.function_list:
            body = self.method_open(func)
            self.calculate_fan_in_fan_out(self.name_list, body, fileinfo, func)

    @staticmethod
    def method_open(func):
        try:
            body = open(func.filename).readlines()[func.start_line:
                                                   func.end_line]
        except IOError:
            body = []
            stderr.write("\nCouldn't open the referenced method inside {0}".
                         format(func.filename))
            stderr.flush()
        return body

    @staticmethod
    def calculate_fan_in_fan_out(name_list, body, fileinfo, func):
        for line in body:
            for i, name in enumerate(name_list):
                re.split(r'; |, |\*|\n', line)
                if name in line:
                    # structural fan-in
                    fileinfo.function_list[i].fan_in += 1
                    # structural fan-out
                    func.fan_out += 1
